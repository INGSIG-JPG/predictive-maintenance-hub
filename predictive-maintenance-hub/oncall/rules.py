"""Load and evaluate alert rules against a telemetry summary."""
from __future__ import annotations

import operator
from dataclasses import dataclass
from pathlib import Path

import yaml

OPERATORS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}
METRICS = {"error_ratio", "p95_ms", "p50_ms", "requests", "errors"}
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "ops" / "alerts" / "alert-rules.yaml"


@dataclass(frozen=True)
class Rule:
    name: str
    journey: str
    metric: str
    operator: str
    threshold: float
    window_seconds: int
    min_requests: int
    severity: str
    summary: str
    responder: str = "escalate"
    runbook: str = ""
    description: str = ""


@dataclass(frozen=True)
class Breach:
    rule: Rule
    value: float
    stats: dict


def load_rules(path: str | Path | None = None) -> list[Rule]:
    raw = yaml.safe_load(Path(path or DEFAULT_RULES_PATH).read_text())
    rules = []
    for item in raw["rules"]:
        rule = Rule(**{k: item[k] for k in item if k in Rule.__dataclass_fields__})
        if rule.operator not in OPERATORS:
            raise ValueError(f"rule {rule.name}: unsupported operator {rule.operator!r}")
        if rule.metric not in METRICS:
            raise ValueError(f"rule {rule.name}: unsupported metric {rule.metric!r}")
        if rule.responder not in {"auto", "escalate"}:
            raise ValueError(f"rule {rule.name}: responder must be 'auto' or 'escalate'")
        rules.append(rule)
    names = [r.name for r in rules]
    if len(names) != len(set(names)):
        raise ValueError("duplicate rule names")
    return rules


def evaluate(rule: Rule, summary: dict) -> Breach | None:
    """Return a Breach when the journey's metric violates the rule with enough traffic to judge."""
    stats = summary.get("journeys", {}).get(rule.journey)
    if not stats or stats["requests"] < rule.min_requests:
        return None
    value = stats[rule.metric]
    return Breach(rule, value, stats) if OPERATORS[rule.operator](value, rule.threshold) else None
