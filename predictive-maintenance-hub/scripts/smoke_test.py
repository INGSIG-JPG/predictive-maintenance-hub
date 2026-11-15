"""Post-deploy smoke test:  python scripts/smoke_test.py https://your-app.example.com
Exercises the key journey end to end (health, create/read data, observability) and exits non-zero on failure."""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

HUB = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"


def call(method, path, body=None):
    req = urllib.request.Request(HUB + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" - {detail}" if detail and not ok else ""))
    if not ok:
        sys.exit(1)


def main():
    for attempt in range(30):  # a fresh deploy may need a moment to boot
        try:
            if call("GET", "/ready")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(2)
    check("service is ready", call("GET", "/ready")[0] == 200)
    code = "SMK-" + uuid.uuid4().hex[:8].upper()
    status, _, _ = call("POST", "/api/machines", {"code": code, "name": "Smoke test machine", "machine_type": "other"})
    check("machine can be registered", status == 201, status)
    status, body, headers = call("POST", "/api/readings", {"machine_code": code, "temperature_c": 105, "vibration_mm_s": 14, "pressure_bar": 9.5})
    data = json.loads(body)
    check("reading is stored and scored critical", status == 201 and data["reading"]["risk_level"] == "critical", status)
    check("a work order was opened", data["work_order"] is not None)
    trace_id = headers.get("X-Trace-Id", "")
    status, body, _ = call("GET", f"/api/telemetry/traces/{trace_id}")
    check("trace for the request is queryable", status == 200 and json.loads(body)["spans"], status)
    check("UI is served", b"Predictive Maintenance Hub" in call("GET", "/")[1])
    check("metrics endpoint works", b"pdm_journey_error_ratio" in call("GET", "/metrics")[1])
    print("smoke test passed")


if __name__ == "__main__":
    main()
