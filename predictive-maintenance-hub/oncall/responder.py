"""On-call responder agent.

Wakes up on an alert (webhook), diagnoses it from traces and config history, applies the ONE
action it is allowed to take (roll a bad config back to the last known-good value), verifies
the fix with a canary request, resolves the alert and writes an incident report.

It is a runbook-driven agent: deterministic, auditable and permission-limited
(see docs/oncall-agent.md and docs/permissions.md). Anything it does not recognise is escalated.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .client import HubClient, HubError

log = logging.getLogger("oncall.responder")

CANARY_CODE = "CANARY-001"
CANARY_VALUES = {"temperature_c": 45.0, "vibration_mm_s": 1.2, "pressure_bar": 6.0}
ALLOWED_ACTIONS = {"config_rollback"}  # guardrail: the complete list of write actions
CONFIG_ERROR_MARKER = "unknown risk model"


class Responder:
    def __init__(self, hub: HubClient, dry_run: bool = False, canary_attempts: int = 3):
        self.hub = hub
        self.dry_run = dry_run
        self.canary_attempts = canary_attempts
        self._lock = threading.Lock()  # one incident at a time

    # ------------------------------------------------------------------ diagnosis
    def diagnose(self, alert: dict) -> dict:
        journey = alert["details"].get("journey", "ingest_reading")
        traces = self.hub.error_traces(journey, limit=20)
        messages = [t["error_message"] for t in traces if t.get("error_message")]
        config_related = [m for m in messages if CONFIG_ERROR_MARKER in m.lower()]
        state = self.hub.config_state()
        current = state["values"].get("risk_model")
        verified = state["verified"].get("risk_model", True)
        if messages and len(config_related) * 2 > len(messages) and not verified:
            cause = "bad_risk_model_config"
        else:
            cause = "unknown"
        return {
            "cause": cause,
            "error_traces": len(traces),
            "sample_errors": sorted(set(messages))[:3],
            "trace_ids": [t["trace_id"] for t in traces][:10],
            "risk_model": current,
            "risk_model_verified": verified,
        }

    # ------------------------------------------------------------------ remediation
    def _act(self, action: str, actions: list[dict], **kwargs) -> dict:
        if action not in ALLOWED_ACTIONS:  # defensive: guards against future code changes
            raise PermissionError(f"action '{action}' is not permitted for the on-call agent")
        record = {"type": action, **kwargs}
        if self.dry_run:
            record["dry_run"] = True
            actions.append(record)
            return record
        result = self.hub.rollback_config(kwargs["key"])
        record.update(result)
        actions.append(record)
        return record

    def verify(self) -> bool:
        """The journey must succeed `canary_attempts` times in a row."""
        return all(self.hub.send_canary_reading(CANARY_CODE, CANARY_VALUES) == 201 for _ in range(self.canary_attempts))

    def handle(self, alert: dict) -> dict:
        """Run the full runbook for one alert and return the incident that was recorded."""
        with self._lock:
            return self._handle(alert)

    def _handle(self, alert: dict) -> dict:
        actions: list[dict] = []
        log.info("woken by alert %s (%s)", alert["id"], alert["rule"])
        responder_mode = alert["details"].get("responder", "auto")
        diagnosis = self.diagnose(alert)
        status, summary = "escalated", ""

        if responder_mode != "auto":
            summary = f"Rule '{alert['rule']}' has no safe automated fix; escalating to a human. Runbook: {alert['details'].get('runbook', 'n/a')}."
        elif diagnosis["cause"] != "bad_risk_model_config":
            summary = (
                "Could not attribute the failures to a bad configuration push "
                f"(sample errors: {diagnosis['sample_errors'] or 'none'}); no action taken, escalating."
            )
        else:
            bad_value = diagnosis["risk_model"]
            try:
                self._act("config_rollback", actions, key="risk_model")
            except HubError as exc:
                summary = f"Rollback of risk_model failed ({exc}); escalating."
            else:
                if self.dry_run:
                    status, summary = "dry_run", f"DRY RUN: would roll risk_model '{bad_value}' back to the last known-good value."
                elif self.verify():
                    self.hub.verify_config("risk_model")
                    status = "resolved"
                    summary = (
                        f"Errors were caused by risk_model='{bad_value}'. Rolled back to '{actions[-1]['to']}'; "
                        f"{self.canary_attempts} canary readings succeeded."
                    )
                else:
                    summary = "Rolled back risk_model but the canary journey still fails; escalating."

        incident = self.hub.record_incident(
            {
                "alert_id": alert["id"], "status": status, "summary": summary,
                "actions": actions + [{"type": "diagnosis", **{k: v for k, v in diagnosis.items() if k != "trace_ids"}}],
                "trace_ids": diagnosis["trace_ids"],
            }
        )
        if status == "resolved":
            self.hub.resolve_alert(alert["id"])
        log.info("incident %s recorded with status %s", incident["id"], status)
        return incident


# ---------------------------------------------------------------------- webhook server

def make_server(responder: Responder, host: str, port: int, secret: str, background: bool = True) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            self._reply(200, {"status": "ok"}) if self.path == "/healthz" else self._reply(404, {"error": "not_found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/alert":
                return self._reply(404, {"error": "not_found"})
            supplied = self.headers.get("X-Webhook-Secret", "")
            if not secret or not hmac.compare_digest(supplied.encode(), secret.encode()):
                return self._reply(401, {"error": "unauthorized"})
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                alert = payload["alert"]
                alert["id"], alert["rule"], alert["details"]
            except (ValueError, KeyError, TypeError):
                return self._reply(400, {"error": "bad_request"})
            if background:
                threading.Thread(target=self._run, args=(alert,), daemon=True).start()
                return self._reply(202, {"status": "accepted"})
            self._reply(200, {"incident": responder.handle(alert)})

        def _run(self, alert):
            try:
                responder.handle(alert)
            except Exception:  # noqa: BLE001 - never crash the server thread
                log.exception("responder failed for alert %s", alert.get("id"))

        def log_message(self, fmt, *args):  # route http.server logs through logging
            log.debug(fmt, *args)

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    secret = os.environ["WEBHOOK_SECRET"]
    hub = HubClient(os.environ.get("HUB_URL", "http://localhost:8000"), os.environ["ADMIN_TOKEN"])
    responder = Responder(hub, dry_run=os.getenv("RESPONDER_DRY_RUN", "false").lower() == "true")
    server = make_server(responder, "0.0.0.0", int(os.getenv("RESPONDER_PORT", "9000")), secret)
    log.info("responder listening on %s (dry_run=%s)", server.server_address, responder.dry_run)
    server.serve_forever()


if __name__ == "__main__":
    main()
