"""Incident drill: push a bad config, generate traffic and wait for the on-call agent to repair it.

Usage: python scripts/simulate_incident.py [HUB_URL]   (needs the alerter + responder running, e.g. `make up`)
Env:   ADMIN_TOKEN (default dev-admin-token). Requires ENABLE_FAULT_INJECTION=true on the target.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HUB = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
TOKEN = os.getenv("ADMIN_TOKEN", "dev-admin-token")


def call(method, path, body=None, auth=False):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(HUB + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def reading():
    return call("POST", "/api/readings", {"machine_code": "PUMP-001", "temperature_c": 50, "vibration_mm_s": 1.5, "pressure_bar": 6})


def main():
    call("POST", "/api/machines", {"code": "PUMP-001", "name": "Cooling pump", "machine_type": "pump"})
    print("1. healthy:", reading()[0])
    status, body = call("PUT", "/admin/config/risk_model", {"value": "v3-experimental", "skip_validation": True}, auth=True)
    print("2. pushed unvalidated config ->", status, body)
    deadline = time.time() + 180
    while time.time() < deadline:
        codes = [reading()[0] for _ in range(5)]
        incidents = call("GET", "/api/incidents")[1].get("items", [])
        print(f"   journey status codes: {codes}  incidents: {len(incidents)}")
        if incidents and set(codes) == {201}:
            print("3. recovered. Incident report:")
            print(json.dumps(incidents[0], indent=2))
            return 0
        time.sleep(4)
    print("The on-call agent did not recover the system within 3 minutes", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
