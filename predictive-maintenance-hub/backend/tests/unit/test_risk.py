import pytest

from app import risk

pytestmark = pytest.mark.unit

NORMAL = {"temperature_c": 45.0, "vibration_mm_s": 1.2, "pressure_bar": 6.0}


def test_normal_values_score_low():
    result = risk.score_reading("v1", NORMAL)
    assert result.score == 0.0
    assert result.level == "low"


def test_all_limits_exceeded_scores_100_critical():
    result = risk.score_reading("v1", {"temperature_c": 120, "vibration_mm_s": 20, "pressure_bar": 12})
    assert result.score == 100.0
    assert result.level == "critical"


def test_single_critical_vibration_is_at_least_high():
    result = risk.score_reading("v1", {**NORMAL, "vibration_mm_s": 12.0})
    assert result.level == "high"


def test_pressure_deviation_is_symmetric():
    low = risk.score_reading("v1", {**NORMAL, "pressure_bar": 2.5}).score
    high = risk.score_reading("v1", {**NORMAL, "pressure_bar": 9.5}).score
    assert low == high > 0


def test_pressure_inside_deadband_contributes_nothing():
    assert risk.score_reading("v1", {**NORMAL, "pressure_bar": 6.9}).score == 0.0


@pytest.mark.parametrize(
    "score,level",
    [(0, "low"), (39.9, "low"), (40, "medium"), (69.9, "medium"), (70, "high"), (84.9, "high"), (85, "critical"), (100, "critical")],
)
def test_level_boundaries(score, level):
    assert risk.level_for(score) == level


def test_v2_adds_bonus_for_statistical_outlier():
    history = {k: [v + (0.1 if i % 2 else -0.1) for i in range(30)] for k, v in NORMAL.items()}
    spike = {**NORMAL, "temperature_c": 59.0}  # below the warning limit -> v1 score is 0
    assert risk.score_reading("v1", spike).score == 0.0
    v2 = risk.score_reading("v2", spike, history)
    assert v2.score == risk.ANOMALY_MAX_BONUS
    assert v2.contributions["anomaly_bonus"] == risk.ANOMALY_MAX_BONUS


def test_v2_ignores_history_when_too_short():
    history = {k: [v] * 3 for k, v in NORMAL.items()}
    assert risk.score_reading("v2", {**NORMAL, "temperature_c": 59.0}, history).score == 0.0


def test_score_never_exceeds_100():
    history = {k: [1.0] * 30 for k in NORMAL}
    assert risk.score_reading("v2", {"temperature_c": 200, "vibration_mm_s": 50, "pressure_bar": 30}, history).score == 100.0


def test_unknown_model_raises_clear_error():
    with pytest.raises(risk.UnknownModelError, match="unknown risk model 'v9'"):
        risk.score_reading("v9", NORMAL)


def test_needs_history():
    assert risk.needs_history("v2") is True
    assert risk.needs_history("v1") is False
    assert risk.needs_history("nope") is False
