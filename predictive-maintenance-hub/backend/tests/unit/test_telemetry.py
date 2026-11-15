import json

import pytest

from app import telemetry

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_context():
    yield
    telemetry.end_trace()


def test_parse_valid_traceparent():
    header = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    assert telemetry.parse_traceparent(header) == ("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7")


@pytest.mark.parametrize(
    "header",
    [None, "", "garbage", "00-short-00f067aa0ba902b7-01",
     "00-00000000000000000000000000000000-00f067aa0ba902b7-01",
     "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"],
)
def test_parse_invalid_traceparent(header):
    assert telemetry.parse_traceparent(header) is None


def test_begin_trace_generates_ids_when_no_header():
    ctx = telemetry.begin_trace(None)
    assert len(ctx.trace_id) == 32 and ctx.remote_parent is None


def test_begin_trace_honours_incoming_header():
    ctx = telemetry.begin_trace("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    assert ctx.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert ctx.remote_parent == "00f067aa0ba902b7"


def test_nested_spans_link_parent_and_child():
    ctx = telemetry.begin_trace()
    with telemetry.span("outer"):
        with telemetry.span("inner", answer=42):
            pass
    inner, outer = ctx.spans
    assert inner.name == "inner" and outer.name == "outer"
    assert inner.parent_span_id == outer.span_id
    assert inner.attributes == {"answer": 42}
    assert inner.trace_id == outer.trace_id == ctx.trace_id


def test_span_records_exception_and_reraises():
    ctx = telemetry.begin_trace()
    with pytest.raises(ValueError):
        with telemetry.span("boom"):
            raise ValueError("bad thing")
    (span,) = ctx.spans
    assert span.status == "error"
    assert span.error_message == "ValueError: bad thing"


def test_span_without_trace_is_a_noop():
    with telemetry.span("orphan") as s:
        assert s is None


def test_log_uses_current_trace_and_span_ids(capsys):
    ctx = telemetry.begin_trace()
    with telemetry.span("work") as s:
        telemetry.log("info", "hello", machine_id=7)
    line = json.loads(capsys.readouterr().out.strip())
    assert line["trace_id"] == ctx.trace_id
    assert line["span_id"] == s.span_id
    assert line["message"] == "hello" and line["machine_id"] == 7
    assert ctx.logs[0]["trace_id"] == ctx.trace_id


def test_sanitize_redacts_sensitive_keys_and_values():
    data = {
        "api_token": "abc", "Authorization": "Bearer xyz", "assigned_to": "jane@example.com",
        "note": "contact jane@example.com or use Bearer abc.def", "ok": 5, "nested": {"password": "p", "fine": "yes"},
    }
    clean = telemetry.sanitize(data)
    assert clean["api_token"] == clean["Authorization"] == clean["assigned_to"] == "[REDACTED]"
    assert "jane@example.com" not in clean["note"] and "abc.def" not in clean["note"]
    assert clean["nested"] == {"password": "[REDACTED]", "fine": "yes"}
    assert clean["ok"] == 5


def test_sanitize_truncates_long_strings():
    assert len(telemetry.sanitize("x" * 1000)) == telemetry.MAX_STR


def test_percentile_nearest_rank():
    values = list(range(1, 101))
    assert telemetry._percentile(values, 50) == 50
    assert telemetry._percentile(values, 95) == 95
    assert telemetry._percentile([], 95) == 0.0
