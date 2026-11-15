"""openapi.yaml is the contract: routes must match it and real responses must validate against it."""
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from helpers import CRITICAL, NORMAL, post_reading

pytestmark = pytest.mark.integration

SPEC = yaml.safe_load((Path(__file__).resolve().parents[3] / "openapi.yaml").read_text())
NON_API_ROUTES = {"/", "/observability", "/static/<path:filename>"}


def _flask_routes(app):
    routes = set()
    for rule in app.url_map.iter_rules():
        if rule.rule in NON_API_ROUTES:
            continue
        path = re.sub(r"<(?:int:)?(\w+)>", r"{\1}", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            routes.add((method.lower(), path))
    return routes


def _normalise(path):
    """The spec uses descriptive parameter names; compare by shape."""
    return re.sub(r"\{[^}]+\}", "{}", path)


def test_every_route_is_documented_and_every_documented_route_exists(app):
    implemented = {(m, _normalise(p)) for m, p in _flask_routes(app)}
    documented = {
        (method, _normalise(path))
        for path, item in SPEC["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert implemented - documented == set(), "routes missing from openapi.yaml"
    assert documented - implemented == set(), "documented routes not implemented"


def _validator(schema):
    wrapped = {"components": SPEC["components"], **schema}
    Draft202012Validator.check_schema(wrapped)
    return Draft202012Validator(wrapped)


def assert_contract(response, method, path):
    operation = SPEC["paths"][path][method]
    declared = operation["responses"]
    assert str(response.status_code) in declared, f"{method.upper()} {path} returned undocumented status {response.status_code}"
    content = declared[str(response.status_code)].get("content", {})
    if "application/json" in content:
        errors = list(_validator(content["application/json"]["schema"]).iter_errors(response.get_json()))
        assert not errors, f"{method.upper()} {path} -> {response.status_code}: {[e.message for e in errors][:3]}"


def test_spec_is_valid_openapi_shape():
    assert SPEC["openapi"].startswith("3.1")
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                assert op.get("operationId"), f"{method} {path} lacks operationId"
                assert op.get("responses"), f"{method} {path} lacks responses"
    for name in SPEC["components"]["schemas"]:
        _validator({"$ref": f"#/components/schemas/{name}"})


def test_request_bodies_in_the_spec_accept_what_the_tests_send():
    create = _validator({"$ref": "#/components/schemas/ReadingCreate"})
    assert not list(create.iter_errors({"machine_code": "A-1", **NORMAL}))
    assert list(create.iter_errors({"machine_code": "A-1", "temperature_c": 9999, "vibration_mm_s": 1, "pressure_bar": 1}))


def test_responses_match_the_contract(client, machine, admin):
    checks = []

    def check(resp, method, path):
        assert_contract(resp, method, path)
        checks.append((method, path, resp.status_code))

    check(client.get("/health"), "get", "/health")
    check(client.get("/ready"), "get", "/ready")
    check(client.get("/api/dashboard/summary"), "get", "/api/dashboard/summary")
    check(client.get("/api/machines"), "get", "/api/machines")
    check(client.post("/api/machines", json={"code": "FAN-003", "name": "Fan", "machine_type": "fan"}), "post", "/api/machines")
    check(client.post("/api/machines", json={"code": "FAN-003", "name": "Fan", "machine_type": "fan"}), "post", "/api/machines")
    check(client.post("/api/machines", json={}), "post", "/api/machines")
    check(client.get(f"/api/machines/{machine['id']}"), "get", "/api/machines/{machineId}")
    check(client.get("/api/machines/999"), "get", "/api/machines/{machineId}")

    ok = post_reading(client, "PUMP-001", CRITICAL)
    check(ok, "post", "/api/readings")
    check(post_reading(client, "NOPE-1"), "post", "/api/readings")
    check(client.post("/api/readings", json={"machine_code": "PUMP-001"}), "post", "/api/readings")
    check(client.get(f"/api/machines/{machine['id']}/readings"), "get", "/api/machines/{machineId}/readings")
    check(client.get("/api/machines/999/readings"), "get", "/api/machines/{machineId}/readings")

    wo_id = ok.get_json()["work_order"]["id"]
    check(client.get("/api/work-orders"), "get", "/api/work-orders")
    check(client.get("/api/work-orders?status=zzz"), "get", "/api/work-orders")
    check(client.patch(f"/api/work-orders/{wo_id}", json={"status": "in_progress", "assigned_to": None}), "patch", "/api/work-orders/{workOrderId}")
    check(client.patch(f"/api/work-orders/{wo_id}", json={"status": "bogus"}), "patch", "/api/work-orders/{workOrderId}")
    check(client.patch("/api/work-orders/999", json={"status": "done"}), "patch", "/api/work-orders/{workOrderId}")
    client.patch(f"/api/work-orders/{wo_id}", json={"status": "done"})
    check(client.patch(f"/api/work-orders/{wo_id}", json={"status": "open"}), "patch", "/api/work-orders/{workOrderId}")

    check(client.get("/api/telemetry/summary"), "get", "/api/telemetry/summary")
    check(client.get("/api/telemetry/summary?after=x"), "get", "/api/telemetry/summary")
    check(client.get("/api/telemetry/traces"), "get", "/api/telemetry/traces")
    check(client.get(f"/api/telemetry/traces/{ok.headers['X-Trace-Id']}"), "get", "/api/telemetry/traces/{traceId}")
    check(client.get("/api/telemetry/traces/unknown"), "get", "/api/telemetry/traces/{traceId}")
    assert client.get("/metrics").mimetype == "text/plain"

    alert = client.post("/api/alerts", json={"rule": "r", "severity": "warning", "summary": "s", "details": {"a": 1}}, headers=admin)
    check(alert, "post", "/api/alerts")
    check(client.post("/api/alerts", json={}, headers=admin), "post", "/api/alerts")
    check(client.post("/api/alerts", json={}), "post", "/api/alerts")
    check(client.get("/api/alerts"), "get", "/api/alerts")
    alert_id = alert.get_json()["id"]
    check(client.patch(f"/api/alerts/{alert_id}", json={"status": "resolved"}, headers=admin), "patch", "/api/alerts/{alertId}")
    check(client.patch("/api/alerts/999", json={"status": "resolved"}, headers=admin), "patch", "/api/alerts/{alertId}")
    check(client.patch(f"/api/alerts/{alert_id}", json={"status": "x"}, headers=admin), "patch", "/api/alerts/{alertId}")
    check(client.patch(f"/api/alerts/{alert_id}", json={"status": "resolved"}), "patch", "/api/alerts/{alertId}")
    check(client.post("/api/incidents", json={"alert_id": alert_id, "status": "resolved", "summary": "done", "actions": [{"a": 1}], "trace_ids": ["t"]}, headers=admin), "post", "/api/incidents")
    check(client.post("/api/incidents", json={"status": "nope"}, headers=admin), "post", "/api/incidents")
    check(client.post("/api/incidents", json={}), "post", "/api/incidents")
    check(client.get("/api/incidents"), "get", "/api/incidents")

    check(client.get("/admin/config", headers=admin), "get", "/admin/config")
    check(client.get("/admin/config"), "get", "/admin/config")
    check(client.put("/admin/config/risk_model", json={"value": "v1"}, headers=admin), "put", "/admin/config/{key}")
    check(client.put("/admin/config/risk_model", json={"value": "zzz"}, headers=admin), "put", "/admin/config/{key}")
    check(client.put("/admin/config/risk_model", json={"value": "v1"}), "put", "/admin/config/{key}")
    check(client.put("/admin/config/nope", json={"value": "v1"}, headers=admin), "put", "/admin/config/{key}")
    check(client.post("/admin/config/risk_model/verify", headers=admin), "post", "/admin/config/{key}/verify")
    check(client.post("/admin/config/nope/verify", headers=admin), "post", "/admin/config/{key}/verify")
    check(client.post("/admin/config/risk_model/rollback", headers=admin), "post", "/admin/config/{key}/rollback")
    check(client.post("/admin/config/risk_model/rollback", headers=admin), "post", "/admin/config/{key}/rollback")
    check(client.post("/admin/config/nope/rollback", headers=admin), "post", "/admin/config/{key}/rollback")

    client.put("/admin/config/risk_model", json={"value": "bad", "skip_validation": True}, headers=admin)
    check(post_reading(client, "PUMP-001"), "post", "/api/readings")  # 500 is part of the contract
    assert len(checks) > 45
