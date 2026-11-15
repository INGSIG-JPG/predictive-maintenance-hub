"""Admin config, rollback, alerts and incidents: the primitives the on-call agent relies on."""
import pytest

from helpers import NORMAL, post_reading

pytestmark = pytest.mark.integration


def test_admin_endpoints_require_a_valid_token(client):
    assert client.get("/admin/config").status_code == 401
    assert client.get("/admin/config", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/admin/config", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.post("/api/alerts", json={}).status_code == 401
    assert client.post("/api/incidents", json={}).status_code == 401
    assert client.patch("/api/alerts/1", json={"status": "resolved"}).status_code == 401
    assert client.get("/admin/config").headers["WWW-Authenticate"] == "Bearer"


def test_initial_config_is_seeded_and_verified(client, admin):
    state = client.get("/admin/config", headers=admin).get_json()
    assert state["values"] == {"risk_model": "v2", "auto_work_orders": "true"}
    assert state["verified"]["risk_model"] is True
    assert state["history"][0]["changed_by"] == "seed"


def test_validated_config_change_rejects_unknown_values(client, admin):
    resp = client.put("/admin/config/risk_model", json={"value": "v3-experimental"}, headers=admin)
    assert resp.status_code == 422
    assert client.put("/admin/config/nope", json={"value": "x"}, headers=admin).status_code == 404
    assert client.put("/admin/config/risk_model", json={"value": ""}, headers=admin).status_code == 422


def test_valid_change_is_unverified_until_verified(client, admin):
    client.put("/admin/config/risk_model", json={"value": "v1"}, headers=admin)
    assert client.get("/admin/config", headers=admin).get_json()["verified"]["risk_model"] is False
    assert client.post("/admin/config/risk_model/verify", headers=admin).get_json()["verified"] is True
    assert client.get("/admin/config", headers=admin).get_json()["verified"]["risk_model"] is True


def test_fault_injection_breaks_the_journey_and_rollback_fixes_it(client, machine, admin):
    assert post_reading(client, "PUMP-001").status_code == 201
    bad = client.put("/admin/config/risk_model", json={"value": "v3-experimental", "skip_validation": True}, headers=admin)
    assert bad.status_code == 200 and bad.get_json()["previous"] == "v2"
    broken = post_reading(client, "PUMP-001")
    assert broken.status_code == 500
    assert broken.get_json()["error"] == "internal_error" and broken.get_json()["trace_id"] == broken.headers["X-Trace-Id"]
    rolled = client.post("/admin/config/risk_model/rollback", headers=admin)
    assert rolled.get_json() == {"key": "risk_model", "from": "v3-experimental", "to": "v2"}
    assert post_reading(client, "PUMP-001").status_code == 201
    history = client.get("/admin/config", headers=admin).get_json()["history"]
    assert history[0]["changed_by"].startswith("rollback:") and history[0]["verified_good"] is True


def test_rollback_without_known_good_value_conflicts(client, admin):
    assert client.post("/admin/config/risk_model/rollback", headers=admin).status_code == 409
    assert client.post("/admin/config/nope/rollback", headers=admin).status_code == 404


def test_verify_refuses_an_invalid_current_value(client, admin):
    client.put("/admin/config/risk_model", json={"value": "zzz", "skip_validation": True}, headers=admin)
    assert client.post("/admin/config/risk_model/verify", headers=admin).status_code == 409


def test_skip_validation_is_forbidden_when_fault_injection_is_off(make_app):
    locked = make_app(enable_fault_injection=False).test_client()
    resp = locked.put(
        "/admin/config/risk_model", json={"value": "bad", "skip_validation": True},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert resp.status_code == 403


def test_alert_lifecycle(client, admin):
    payload = {"rule": "r1", "severity": "critical", "summary": "boom", "details": {"error_ratio": 0.5}}
    created = client.post("/api/alerts", json=payload, headers=admin)
    assert created.status_code == 201 and created.get_json()["status"] == "firing"
    alert_id = created.get_json()["id"]
    assert [a["id"] for a in client.get("/api/alerts?status=firing").get_json()["items"]] == [alert_id]
    resolved = client.patch(f"/api/alerts/{alert_id}", json={"status": "resolved"}, headers=admin).get_json()
    assert resolved["status"] == "resolved" and resolved["resolved_at"]
    assert client.get("/api/alerts?status=firing").get_json()["items"] == []
    assert client.get("/api/alerts?rule=r1&status=resolved").get_json()["items"][0]["id"] == alert_id
    assert client.patch(f"/api/alerts/{alert_id}", json={"status": "firing"}, headers=admin).status_code == 422
    assert client.patch("/api/alerts/999", json={"status": "resolved"}, headers=admin).status_code == 404
    assert client.post("/api/alerts", json={"rule": "r", "severity": "meh", "summary": "s"}, headers=admin).status_code == 422


def test_incident_recording(client, admin):
    alert = client.post("/api/alerts", json={"rule": "r1", "severity": "critical", "summary": "boom"}, headers=admin).get_json()
    body = {"alert_id": alert["id"], "status": "resolved", "summary": "rolled back", "actions": [{"type": "config_rollback"}], "trace_ids": ["abc"]}
    created = client.post("/api/incidents", json=body, headers=admin)
    assert created.status_code == 201
    assert created.get_json()["actions"] == [{"type": "config_rollback"}]
    assert client.get("/api/incidents").get_json()["items"][0]["alert_id"] == alert["id"]
    assert client.post("/api/incidents", json={**body, "status": "weird"}, headers=admin).status_code == 422
    assert client.post("/api/incidents", json={**body, "alert_id": 999}, headers=admin).status_code == 404
    assert client.post("/api/incidents", json={**body, "actions": "x"}, headers=admin).status_code == 422


def test_unknown_route_returns_json_404(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"
