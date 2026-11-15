"""Pure risk scoring logic (no I/O). Deterministic and unit-tested.

The scores are a transparent, threshold-based heuristic for prioritising inspections.
They are NOT a calibrated failure probability.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# (warning, critical) limits. Values at or below warning contribute 0, at or above
# critical contribute 1, linear in between. Limits are illustrative defaults.
LIMITS = {
    "temperature_c": (60.0, 95.0),
    "vibration_mm_s": (2.8, 11.2),
}
PRESSURE_NOMINAL_BAR = 6.0
PRESSURE_DEADBAND_BAR = 1.0
PRESSURE_CRITICAL_DEVIATION_BAR = 3.0

WEIGHTS = {"temperature_c": 0.35, "vibration_mm_s": 0.45, "pressure_bar": 0.20}

LEVEL_THRESHOLDS = [(85.0, "critical"), (70.0, "high"), (40.0, "medium"), (0.0, "low")]

HISTORY_MIN_POINTS = 10
ANOMALY_Z_START = 2.0
ANOMALY_Z_FULL = 4.0
ANOMALY_MAX_BONUS = 15.0


class UnknownModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class RiskResult:
    score: float
    level: str
    contributions: dict
    model: str


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _ramp(value: float, warn: float, crit: float) -> float:
    return _clamp((value - warn) / (crit - warn))


def level_for(score: float) -> str:
    for threshold, name in LEVEL_THRESHOLDS:
        if score >= threshold:
            return name
    return "low"


def normalized_exceedance(values: dict) -> dict:
    return {
        "temperature_c": _ramp(values["temperature_c"], *LIMITS["temperature_c"]),
        "vibration_mm_s": _ramp(values["vibration_mm_s"], *LIMITS["vibration_mm_s"]),
        "pressure_bar": _clamp(
            (abs(values["pressure_bar"] - PRESSURE_NOMINAL_BAR) - PRESSURE_DEADBAND_BAR)
            / (PRESSURE_CRITICAL_DEVIATION_BAR - PRESSURE_DEADBAND_BAR)
        ),
    }


def base_score(values: dict) -> tuple[float, dict]:
    n = normalized_exceedance(values)
    weighted_mean = sum(WEIGHTS[k] * n[k] for k in WEIGHTS)
    score = 100.0 * min(1.0, 0.6 * max(n.values()) + 0.4 * weighted_mean)
    return score, n


def z_score(value: float, history: list[float]) -> float:
    if len(history) < HISTORY_MIN_POINTS:
        return 0.0
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / len(history)
    std = max(math.sqrt(var), 1e-6)
    return (value - mean) / std


def anomaly_bonus(values: dict, history: dict[str, list[float]]) -> float:
    zs = [z_score(values[k], history.get(k, [])) for k in ("temperature_c", "vibration_mm_s", "pressure_bar")]
    worst = max(zs)
    return ANOMALY_MAX_BONUS * _clamp((worst - ANOMALY_Z_START) / (ANOMALY_Z_FULL - ANOMALY_Z_START))


MODELS = {"v1": False, "v2": True}  # model name -> needs per-machine history


def needs_history(model: str) -> bool:
    return MODELS.get(model, False)


def score_reading(model: str, values: dict, history: dict[str, list[float]] | None = None) -> RiskResult:
    if model not in MODELS:
        raise UnknownModelError(f"unknown risk model '{model}'")
    score, n = base_score(values)
    contributions = {k: round(v, 3) for k, v in n.items()}
    if model == "v2":
        bonus = anomaly_bonus(values, history or {})
        contributions["anomaly_bonus"] = round(bonus, 3)
        score = min(100.0, score + bonus)
    score = round(score, 1)
    return RiskResult(score=score, level=level_for(score), contributions=contributions, model=model)
