"""End-to-end API behaviour with a real database: the key user journey and persistence."""
import pytest

from app import create_app
from helpers import CRITICAL, NORMAL, post_reading

pytestmark = pytest.mark.integration


def test_health_and_ready(client):
    assert client.get("/health").get_json() == {"status": "ok"}
    assert client.get("/ready").get_json() == {"status": "ready"}


def test_machine_lifecycle(client):
    created = client.post("/api/machines", json={"code": "MOTOR-014", "name": "Drive motor", "machine_type": "motor"})
    assert created.status_code == 201
    body = created.get_json()
    assert body["latest_risk_level"] is None and body["location"] == ""
    assert client.get(f"/api/machines/{body['id']}").get_json()["code"] == "MOTOR-014"
    listing = client.get("/api/machines").get_json()["items"]
    assert [m["code"] for m in listing] == ["MOTOR-014"]  # canary machine is hidden


def test_duplicate_machine_code_conflicts(client, machine):
    resp = client.post("/api/machines", json={"code": "PUMP-001", "name": "x", "machine_type": "pump"})
    assert resp.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [{}, {"code": "bad code", "name": "x", "machine_type": "pump"}, {"code": "OK-1", "name": "x", "machine_type": "toaster"}, {"code": "OK-1", "name": " ", "machine_type": "pump"}],
)
def test_invalid_machine_is_rejected(client, payload):
    assert client.post("/api/machines", json=payload).status_code == 422


def test_normal_reading_is_scored_low_without_work_order(client, machine):
    resp = post_reading(client, "PUMP-001")
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["reading"]["risk_level"] == "low"
    assert body["work_order"] is None
    assert body["reading"]["model_version"] == "v2"
    assert client.get(f"/api/machines/{machine['id']}").get_json()["latest_risk_level"] == "low"


def test_critical_reading_opens_one_p1_work_order_and_dedupes(client, machine):
    first = post_reading(client, "PUMP-001", CRITICAL).get_json()
    assert first["reading"]["risk_level"] == "critical"
    assert first["work_order"]["priority"] == "P1" and first["work_order"]["status"] == "open"
    assert first["work_order"]["machine_code"] == "PUMP-001"
    second = post_reading(client, "PUMP-001", CRITICAL).get_json()
    assert second["work_order"] is None  # an open work order already exists
    assert len(client.get("/api/work-orders").get_json()["items"]) == 1


def test_work_order_lifecycle_and_invalid_transitions(client, machine):
    wo = post_reading(client, "PUMP-001", CRITICAL).get_json()["work_order"]
    url = f"/api/work-orders/{wo['id']}"
    assert client.patch(url, json={"status": "in_progress", "assigned_to": "maria"}).get_json()["assigned_to"] == "maria"
    assert client.patch(url, json={"status": "done"}).get_json()["status"] == "done"
    assert client.patch(url, json={"status": "open"}).status_code == 409
    assert client.patch(url, json={"status": "bogus"}).status_code == 422
    assert client.patch(url, json={"unknown": 1}).status_code == 422
    assert client.patch(url, json={}).status_code == 422
    assert client.patch("/api/work-orders/9999", json={"status": "done"}).status_code == 404
    assert client.get("/api/work-orders?status=done").get_json()["items"][0]["id"] == wo["id"]
    assert client.get("/api/work-orders?status=bogus").status_code == 422
    # once closed, a new critical reading may open a new work order
    assert post_reading(client, "PUMP-001", CRITICAL).get_json()["work_order"] is not None


def test_reading_for_unknown_machine_is_404_and_invalid_is_422(client):
    assert post_reading(client, "NOPE-1").status_code == 404
    assert client.post("/api/readings", json={"machine_code": "NOPE-1", "temperature_c": "x"}).status_code == 422
    assert client.post("/api/readings", data="not json", content_type="application/json").status_code == 422


def test_readings_history_is_newest_first(client, machine):
    for temp in (40.0, 41.0, 42.0):
        post_reading(client, "PUMP-001", {**NORMAL, "temperature_c": temp})
    items = client.get(f"/api/machines/{machine['id']}/readings?limit=2").get_json()["items"]
    assert [r["temperature_c"] for r in items] == [42.0, 41.0]
    assert client.get("/api/machines/999/readings").status_code == 404
    assert client.get("/api/machines/1/readings?limit=abc").status_code == 422


def test_dashboard_summary(client, machine):
    post_reading(client, "PUMP-001", CRITICAL)
    client.post("/api/machines", json={"code": "FAN-003", "name": "Fan", "machine_type": "fan"})
    summary = client.get("/api/dashboard/summary").get_json()
    assert summary["machines_total"] == 2
    assert summary["by_risk_level"]["critical"] == 1 and summary["by_risk_level"]["unknown"] == 1
    assert summary["open_work_orders"] == 1 and summary["readings_24h"] == 1


def test_data_persists_across_app_instances(app, client, machine):
    """Data is in the database, not in process memory: a brand new app instance sees it."""
    post_reading(client, "PUMP-001", CRITICAL)
    second_app = create_app(app.config["PDM"])
    second = second_app.test_client()
    assert second.get("/api/machines").get_json()["items"][0]["latest_risk_level"] == "critical"
    assert len(second.get("/api/work-orders").get_json()["items"]) == 1


def test_auto_work_orders_can_be_disabled(client, machine, admin):
    assert client.put("/admin/config/auto_work_orders", json={"value": "false"}, headers=admin).status_code == 200
    assert post_reading(client, "PUMP-001", CRITICAL).get_json()["work_order"] is None


def test_frontend_pages_are_served(client):
    assert b"Predictive Maintenance Hub" in client.get("/").data
    assert b"Observability" in client.get("/observability").data
    assert client.get("/static/src/api.js").status_code == 200
    assert client.get("/static/../backend/wsgi.py").status_code in (404, 400)
