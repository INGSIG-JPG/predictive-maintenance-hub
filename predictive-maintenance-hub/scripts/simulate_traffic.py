"""Send realistic sensor traffic to a running instance:  python scripts/simulate_traffic.py [HUB_URL]"""
import json
import random
import sys
import urllib.error
import urllib.request

HUB = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def call(method, path, body=None):
    req = urllib.request.Request(HUB + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    status, body = call("GET", "/api/machines")
    machines = body["items"] if status == 200 else []
    if not machines:
        for code, name, kind in [("PUMP-001", "Cooling pump", "pump"), ("MOTOR-014", "Drive motor", "motor")]:
            call("POST", "/api/machines", {"code": code, "name": name, "machine_type": kind})
        machines = call("GET", "/api/machines")[1]["items"]
    random.seed(7)
    counts = {}
    for i in range(60):
        m = random.choice(machines)
        degraded = i % 15 == 14
        values = {
            "temperature_c": random.gauss(100 if degraded else 50, 3),
            "vibration_mm_s": random.gauss(13 if degraded else 1.5, 0.3),
            "pressure_bar": random.gauss(9 if degraded else 6, 0.2),
        }
        status, _ = call("POST", "/api/readings", {"machine_code": m["code"], **{k: round(max(v, 0), 2) for k, v in values.items()}})
        counts[status] = counts.get(status, 0) + 1
    print("responses by status:", counts)


if __name__ == "__main__":
    main()
