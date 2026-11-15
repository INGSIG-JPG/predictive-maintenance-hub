"""HTTP client for the Hub API used by the alerter and the responder agent."""
from __future__ import annotations

import requests


class HubError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class HubClient:
    def __init__(self, base_url: str, admin_token: str, session: requests.Session | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token = admin_token
        self.session = session or requests.Session()
        self.timeout = timeout

    def request(self, method: str, path: str, *, params=None, json=None, auth: bool = False, expect=(200, 201), actor: str = "oncall-agent"):
        headers = {"X-Actor": actor}
        if auth:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.session.request(
            method, f"{self.base_url}{path}", params=params, json=json, headers=headers, timeout=self.timeout
        )
        if response.status_code not in expect:
            try:
                message = response.json().get("message", response.text[:200])
            except ValueError:
                message = response.text[:200]
            raise HubError(response.status_code, message)
        return response

    # --- read-only
    def telemetry_summary(self, window: int, after: float | None = None) -> dict:
        params = {"window": window}
        if after:
            params["after"] = after
        return self.request("GET", "/api/telemetry/summary", params=params).json()

    def error_traces(self, journey: str, limit: int = 20) -> list[dict]:
        params = {"status": "error", "journey": journey, "limit": limit}
        return self.request("GET", "/api/telemetry/traces", params=params).json()["items"]

    def config_state(self) -> dict:
        return self.request("GET", "/admin/config", auth=True).json()

    def alerts(self, **params) -> list[dict]:
        return self.request("GET", "/api/alerts", params=params).json()["items"]

    # --- writes
    def fire_alert(self, rule: str, severity: str, summary: str, details: dict) -> dict:
        body = {"rule": rule, "severity": severity, "summary": summary, "details": details}
        return self.request("POST", "/api/alerts", json=body, auth=True, actor="alerter").json()

    def resolve_alert(self, alert_id: int, actor: str = "oncall-agent") -> dict:
        return self.request("PATCH", f"/api/alerts/{alert_id}", json={"status": "resolved"}, auth=True, actor=actor).json()

    def rollback_config(self, key: str) -> dict:
        return self.request("POST", f"/admin/config/{key}/rollback", auth=True).json()

    def verify_config(self, key: str) -> dict:
        return self.request("POST", f"/admin/config/{key}/verify", auth=True).json()

    def record_incident(self, body: dict) -> dict:
        return self.request("POST", "/api/incidents", json=body, auth=True).json()

    def send_canary_reading(self, code: str, values: dict) -> int:
        """Probe the key journey with a synthetic reading; returns the HTTP status."""
        response = self.request("POST", "/api/readings", json={"machine_code": code, **values}, expect=range(200, 600))
        return response.status_code
