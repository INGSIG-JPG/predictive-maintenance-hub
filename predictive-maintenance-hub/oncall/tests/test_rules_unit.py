import pytest

from oncall.rules import Rule, evaluate, load_rules

pytestmark = pytest.mark.unit


def _rule(**kw):
    base = dict(name="r", journey="ingest_reading", metric="error_ratio", operator=">", threshold=0.05,
                window_seconds=60, min_requests=5, severity="critical", summary="s", responder="auto")
    base.update(kw)
    return Rule(**base)


def _summary(requests, errors, p95=10.0):
    ratio = errors / requests if requests else 0
    return {"journeys": {"ingest_reading": {"requests": requests, "errors": errors, "error_ratio": ratio, "p50_ms": 5.0, "p95_ms": p95}}}


def test_breach_when_error_ratio_exceeds_threshold():
    breach = evaluate(_rule(), _summary(10, 3))
    assert breach is not None and breach.value == pytest.approx(0.3)


def test_no_breach_below_threshold():
    assert evaluate(_rule(), _summary(100, 4)) is None


def test_no_breach_when_traffic_is_too_low_to_judge():
    assert evaluate(_rule(min_requests=5), _summary(4, 4)) is None


def test_no_breach_when_journey_has_no_traffic():
    assert evaluate(_rule(), {"journeys": {}}) is None


def test_latency_rule_uses_p95():
    rule = _rule(metric="p95_ms", threshold=1500, min_requests=1)
    assert evaluate(rule, _summary(10, 0, p95=2000.0)) is not None
    assert evaluate(rule, _summary(10, 0, p95=900.0)) is None


def test_shipped_rules_are_valid_and_target_user_impact():
    rules = load_rules()
    assert {r.name for r in rules} >= {"ingest_reading_error_rate", "ingest_reading_latency_p95"}
    assert all(r.metric in {"error_ratio", "p95_ms"} for r in rules)  # user impact, never CPU/memory
    assert all(r.journey == "ingest_reading" for r in rules)


def test_invalid_rule_files_are_rejected(tmp_path):
    bad = tmp_path / "r.yaml"
    bad.write_text("rules:\n  - {name: a, journey: j, metric: cpu_percent, operator: '>', threshold: 1, window_seconds: 1, min_requests: 1, severity: critical, summary: s}\n")
    with pytest.raises(ValueError, match="unsupported metric"):
        load_rules(bad)
