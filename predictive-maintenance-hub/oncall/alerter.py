"""Alert trigger: evaluates user-impact rules and wakes the on-call agent when one fires.

Run with ``python -m oncall.alerter`` (loops forever) or call ``Alerter.tick()`` directly.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

import requests

from .client import HubClient, HubError
from .rules import Rule, evaluate, load_rules

log = logging.getLogger("oncall.alerter")


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso).timestamp()


class Alerter:
    def __init__(self, hub: HubClient, rules: list[Rule], responder_url: str | None = None, webhook_secret: str = "", session: requests.Session | None = None):
        self.hub = hub
        self.rules = rules
        self.responder_url = responder_url
        self.webhook_secret = webhook_secret
        self.session = session or requests.Session()

    def _after(self, rule: Rule) -> float | None:
        """Ignore spans from before the last resolution so a fixed incident does not re-fire."""
        resolved = self.hub.alerts(rule=rule.name, status="resolved", limit=1)
        return _epoch(resolved[0]["resolved_at"]) if resolved else None

    def tick(self) -> list[dict]:
        """One evaluation pass. Returns the alerts fired during this pass."""
        fired = []
        for rule in self.rules:
            summary = self.hub.telemetry_summary(rule.window_seconds, after=self._after(rule))
            breach = evaluate(rule, summary)
            firing = self.hub.alerts(rule=rule.name, status="firing", limit=1)
            if breach and not firing:
                alert = self.hub.fire_alert(
                    rule.name, rule.severity, rule.summary,
                    {
                        "journey": rule.journey, "metric": rule.metric, "value": breach.value,
                        "threshold": rule.threshold, "window_seconds": rule.window_seconds,
                        "requests": breach.stats["requests"], "errors": breach.stats["errors"],
                        "responder": rule.responder, "runbook": rule.runbook,
                    },
                )
                log.warning("alert fired: %s (value=%s)", rule.name, breach.value)
                self._wake_responder(alert)
                fired.append(alert)
            elif not breach and firing:
                self.hub.resolve_alert(firing[0]["id"], actor="alerter")
                log.info("alert recovered by itself: %s", rule.name)
        return fired

    def _wake_responder(self, alert: dict) -> None:
        if not self.responder_url:
            log.warning("no RESPONDER_URL configured; alert %s needs a human", alert["id"])
            return
        try:
            response = self.session.post(
                self.responder_url, json={"alert": alert}, headers={"X-Webhook-Secret": self.webhook_secret}, timeout=5
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            log.error("could not wake responder for alert %s: %s", alert["id"], exc)

    def run_forever(self, interval: float) -> None:
        while True:
            try:
                self.tick()
            except (HubError, requests.RequestException) as exc:
                log.error("tick failed: %s", exc)
            time.sleep(interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    hub = HubClient(os.environ.get("HUB_URL", "http://localhost:8000"), os.environ["ADMIN_TOKEN"])
    alerter = Alerter(
        hub, load_rules(os.getenv("ALERT_RULES_PATH")), os.getenv("RESPONDER_URL"), os.getenv("WEBHOOK_SECRET", "")
    )
    alerter.run_forever(float(os.getenv("ALERT_INTERVAL_SECONDS", "15")))


if __name__ == "__main__":
    main()
