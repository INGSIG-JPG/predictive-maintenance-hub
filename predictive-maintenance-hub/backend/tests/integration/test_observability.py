"""Observability requirements: one trace ID across metrics, traces and logs; nothing sensitive stored."""
import json

import pytest

from helpers import CRITICAL, NORMAL, post_reading

pytestmark = pytest.mark.integration


def test_response_carries_trace_id_and_traceparent(client, machine):
    resp = post_reading(client, "PUMP-001")
    trace_id = resp.headers["X-Trace-Id"]
    assert len(trace_id) == 32
    assert resp.headers["traceparent"].startswith(f"00-{trace_id}-")
    assert resp.get_json()["reading"]["trace_id"] == trace_id


def test_spans_and_logs_share_the_response_trace_id(client, machine):
    trace_id = post_reading(client, "PUMP-001", CRITICAL).headers["X-Trace-Id"]
    trace = client.get(f"/api/telemetry/traces/{trace_id}").get_json()
    names = [s["name"] for s in trace["spans"]]
    assert {"http.request", "risk.score", "db.insert_reading", "workorder.create"} <= set(names)
    root = next(s for s in trace["spans"] if s["name"] == "http.request")
    children = [s for s in trace["spans"] if s["name"] != "http.request"]
    assert all(c["parent_span_id"] == root["span_id"] for c in children)
    assert root["attributes"]["journey"] == "ingest_reading"
    messages = {r["message"] for r in trace["logs"]}
    assert {"reading_ingested", "http_request"} <= messages
    span_ids = {s["span_id"] for s in trace["spans"]}
    assert all(r["span_id"] is None or r["span_id"] in span_ids for r in trace["logs"])


def test_incoming_traceparent_is_continued(client, machine):
    incoming = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    resp = client.post("/api/readings", json={"machine_code": "PUMP-001", **NORMAL}, headers={"traceparent": incoming})
    assert resp.headers["X-Trace-Id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    trace = client.get("/api/telemetry/traces/4bf92f3577b34da6a3ce929d0e0e4736").get_json()
    root = next(s for s in trace["spans"] if s["name"] == "http.request")
    assert root["parent_span_id"] == "00f067aa0ba902b7"


def test_failed_request_is_an_error_trace_with_the_cause(client, machine, admin):
    client.put("/admin/config/risk_model", json={"value": "v3-experimental", "skip_validation": True}, headers=admin)
    trace_id = post_reading(client, "PUMP-001").headers["X-Trace-Id"]
    errors = client.get("/api/telemetry/traces?status=error&journey=ingest_reading").get_json()["items"]
    item = next(t for t in errors if t["trace_id"] == trace_id)
    assert item["status_code"] == 500 and "unknown risk model 'v3-experimental'" in item["error_message"]
    trace = client.get(f"/api/telemetry/traces/{trace_id}").get_json()
    assert any(s["name"] == "risk.score" and s["status"] == "error" for s in trace["spans"])
    assert any(r["level"] == "error" and r["message"] == "unhandled_exception" for r in trace["logs"])


def test_summary_reports_journey_error_ratio_and_percentiles(client, machine, admin):
    for _ in range(3):
        post_reading(client, "PUMP-001")
    client.put("/admin/config/risk_model", json={"value": "bad", "skip_validation": True}, headers=admin)
    post_reading(client, "PUMP-001")
    stats = client.get("/api/telemetry/summary?window=60").get_json()["journeys"]["ingest_reading"]
    assert stats["requests"] == 4 and stats["errors"] == 1 and stats["error_ratio"] == 0.25
    assert stats["p95_ms"] >= stats["p50_ms"] > 0


def test_summary_after_parameter_ignores_older_spans(client, machine):
    post_reading(client, "PUMP-001")
    future = client.get("/api/telemetry/summary").get_json()["generated_at"] + 60
    assert client.get(f"/api/telemetry/summary?after={future}").get_json()["journeys"] == {}
    assert client.get("/api/telemetry/summary?after=abc").status_code == 422


def test_metrics_endpoint_uses_prometheus_format(client, machine):
    post_reading(client, "PUMP-001")
    text = client.get("/metrics").get_data(as_text=True)
    assert 'pdm_http_requests{route="/api/readings",status="201"} 1' in text
    assert 'pdm_journey_error_ratio{journey="ingest_reading"} 0.0' in text
    assert "pdm_journey_latency_p95_ms" in text and "pdm_open_work_orders" in text


def test_no_customer_data_or_credentials_reach_telemetry(client, machine, admin):
    """Assignee e-mails and bearer tokens must be redacted everywhere telemetry is stored."""
    wo = post_reading(client, "PUMP-001", CRITICAL).get_json()["work_order"]
    client.patch(f"/api/work-orders/{wo['id']}", json={"assigned_to": "jane.doe@example.com"})
    client.put("/admin/config/risk_model", json={"value": "v1"}, headers=admin)
    client.get("/admin/config", headers=admin)
    with client.application.extensions["pdm_db"].session() as conn:
        dump = json.dumps(conn.query("SELECT * FROM telemetry_spans")) + json.dumps(conn.query("SELECT * FROM telemetry_logs"))
    assert "jane.doe@example.com" not in dump
    assert "test-admin-token" not in dump
    assert "[REDACTED]" in dump  # the assignee log field was redacted rather than dropped silently


def test_operational_endpoints_are_not_recorded(client):
    client.get("/health")
    client.get("/metrics")
    assert client.get("/api/telemetry/traces").get_json()["items"] == []


def test_readiness_fails_when_database_is_unreachable(make_app, monkeypatch):
    application = make_app()
    client = application.test_client()

    def broken_query(self, *a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.db.Conn.query_one", broken_query)
    assert client.get("/ready").status_code == 503
    monkeypatch.undo()
    assert client.get("/ready").status_code == 200
