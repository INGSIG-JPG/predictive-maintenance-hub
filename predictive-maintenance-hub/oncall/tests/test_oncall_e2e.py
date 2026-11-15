"""End to end: a bad config breaks the journey -> alert fires -> responder agent wakes and fixes it."""
import threading

import pytest
import requests

from app import telemetry  # noqa: F401  (ensures the app package is importable)
from helpers import CRITICAL, NORMAL
from oncall.alerter import Alerter
from oncall.client import HubClient
from oncall.responder import Responder, make_server
from oncall.rules import load_rules
from oncall_helpers import ADMIN_TOKEN

pytestmark = pytest.mark.integration

SECRET = "hook-secret"
BAD_CONFIG = {"value": "v3-experimental", "skip_validation": True}
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _traffic(hub_url, n, values=NORMAL, code="PUMP-001"):
    return [requests.post(f"{hub_url}/api/readings", json={"machine_code": code, **values}).status_code for _ in range(n)]


@pytest.fixture()
def world(live_hub):
    """A running hub with one machine, a hub client and the shipped alert rules."""
    requests.post(f"{live_hub.url}/api/machines", json={"code": "PUMP-001", "name": "Pump", "machine_type": "pump"})
    return live_hub, HubClient(live_hub.url, ADMIN_TOKEN), load_rules()


def _break(hub):
    assert requests.put(f"{hub.url}/admin/config/risk_model", json=BAD_CONFIG, headers=ADMIN).status_code == 200


def test_healthy_system_fires_no_alert(world):
    hub, client, rules = world
    assert set(_traffic(hub.url, 10)) == {201}
    assert Alerter(client, rules).tick() == []
    assert client.alerts() == []


def test_low_traffic_does_not_page_anyone(world):
    hub, client, rules = world
    _break(hub)
    assert set(_traffic(hub.url, 2)) == {500}  # below min_requests
    assert Alerter(client, rules).tick() == []


def test_bad_config_fires_alert_and_responder_fixes_it(world):
    hub, client, rules = world
    _traffic(hub.url, 5)
    _break(hub)
    assert set(_traffic(hub.url, 8)) == {500}

    responder = Responder(client)
    server = make_server(responder, "127.0.0.1", 0, SECRET, background=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        alerter = Alerter(client, rules, f"http://127.0.0.1:{server.server_port}/alert", SECRET)
        fired = alerter.tick()  # the alerter wakes the responder synchronously in this test server mode
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert [a["rule"] for a in fired] == ["ingest_reading_error_rate"]
    # The journey works again, with the right model
    assert set(_traffic(hub.url, 3)) == {201}
    assert requests.get(f"{hub.url}/admin/config", headers=ADMIN).json()["values"]["risk_model"] == "v2"
    # The alert was resolved by the agent and an incident report was written
    alert = client.alerts(rule="ingest_reading_error_rate")[0]
    assert alert["status"] == "resolved"
    (incident,) = requests.get(f"{hub.url}/api/incidents").json()["items"]
    assert incident["status"] == "resolved" and incident["alert_id"] == alert["id"]
    assert incident["actions"][0]["type"] == "config_rollback" and incident["actions"][0]["to"] == "v2"
    assert incident["trace_ids"], "incident links to the failing traces"
    assert "v3-experimental" in incident["summary"]
    # A new alerter pass does not re-fire for the already fixed incident
    assert Alerter(client, rules).tick() == []


def test_alert_does_not_fire_twice_while_firing(world):
    hub, client, rules = world
    _break(hub)
    _traffic(hub.url, 8)
    alerter = Alerter(client, rules)  # no responder: alert stays firing
    assert len(alerter.tick()) == 1
    assert alerter.tick() == []
    assert len(client.alerts(status="firing")) == 1


def test_responder_dry_run_changes_nothing(world):
    hub, client, rules = world
    _break(hub)
    _traffic(hub.url, 8)
    alert = Alerter(client, rules).tick()[0]
    incident = Responder(client, dry_run=True).handle(alert)
    assert incident["status"] == "dry_run"
    assert requests.get(f"{hub.url}/admin/config", headers=ADMIN).json()["values"]["risk_model"] == "v3-experimental"


def test_responder_escalates_when_cause_is_not_a_bad_config(world):
    """Guardrail: failures it cannot attribute to a config push are never 'fixed' by guessing."""
    hub, client, _ = world
    alert = client.fire_alert("ingest_reading_error_rate", "critical", "failing", {"journey": "ingest_reading", "responder": "auto"})
    incident = Responder(client).handle(alert)
    assert incident["status"] == "escalated"
    assert "no action taken" in incident["summary"]
    assert [a for a in incident["actions"] if a["type"] == "config_rollback"] == []
    assert client.alerts(status="firing")[0]["id"] == alert["id"]  # left open for a human


def test_responder_escalates_rules_without_an_automatic_fix(world):
    hub, client, _ = world
    alert = client.fire_alert("ingest_reading_latency_p95", "warning", "slow", {"journey": "ingest_reading", "responder": "escalate", "runbook": "docs/runbooks/high-latency.md"})
    incident = Responder(client).handle(alert)
    assert incident["status"] == "escalated" and "high-latency.md" in incident["summary"]


def test_responder_escalates_when_no_known_good_value_exists(world):
    hub, client, rules = world
    _break(hub)
    _traffic(hub.url, 8)
    # wipe the verified history so there is nothing safe to roll back to
    with hub.server.app.extensions["pdm_db"].session() as conn:
        conn.execute("UPDATE config_history SET verified_good = 0")
        conn.commit()
    alert = Alerter(client, rules).tick()[0]
    incident = Responder(client).handle(alert)
    assert incident["status"] == "escalated" and "Rollback of risk_model failed" in incident["summary"]


def test_agent_cannot_perform_actions_outside_its_allow_list(world):
    hub, client, _ = world
    with pytest.raises(PermissionError):
        Responder(client)._act("drop_database", [])


def test_webhook_rejects_bad_secret_and_bad_payloads(world):
    hub, client, _ = world
    server = make_server(Responder(client), "127.0.0.1", 0, SECRET, background=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert requests.post(f"{url}/alert", json={"alert": {}}).status_code == 401
        assert requests.post(f"{url}/alert", json={"alert": {}}, headers={"X-Webhook-Secret": "nope"}).status_code == 401
        assert requests.post(f"{url}/alert", json={"nothing": 1}, headers={"X-Webhook-Secret": SECRET}).status_code == 400
        assert requests.get(f"{url}/healthz").json() == {"status": "ok"}
        assert requests.post(f"{url}/other", json={}).status_code == 404
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_canary_traffic_does_not_pollute_the_dashboard(world):
    hub, client, _ = world
    client.send_canary_reading("CANARY-001", NORMAL)
    summary = requests.get(f"{hub.url}/api/dashboard/summary").json()
    assert summary["machines_total"] == 1 and summary["readings_24h"] == 0
