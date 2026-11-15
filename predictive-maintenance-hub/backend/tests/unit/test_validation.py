import pytest

from app import services
from app.errors import ValidationError

pytestmark = pytest.mark.unit

GOOD = {"machine_code": "PUMP-001", "temperature_c": 50, "vibration_mm_s": 2, "pressure_bar": 6}


def test_valid_reading_passes_and_normalises_timestamp():
    data = services.validate_reading({**GOOD, "recorded_at": "2026-01-02T03:04:05Z"})
    assert data["recorded_at"] == "2026-01-02T03:04:05+00:00"
    assert data["temperature_c"] == 50.0


@pytest.mark.parametrize(
    "patch,field",
    [
        ({"machine_code": ""}, "machine_code"),
        ({"machine_code": None}, "machine_code"),
        ({"temperature_c": "hot"}, "temperature_c"),
        ({"temperature_c": True}, "temperature_c"),
        ({"temperature_c": 1000}, "temperature_c"),
        ({"vibration_mm_s": -1}, "vibration_mm_s"),
        ({"pressure_bar": float("nan")}, "pressure_bar"),
        ({"recorded_at": "yesterday"}, "recorded_at"),
        ({"recorded_at": 5}, "recorded_at"),
    ],
)
def test_invalid_reading_fields_are_rejected(patch, field):
    with pytest.raises(ValidationError) as err:
        services.validate_reading({**GOOD, **patch})
    assert err.value.field == field


def test_missing_field_is_rejected():
    payload = dict(GOOD)
    del payload["pressure_bar"]
    with pytest.raises(ValidationError):
        services.validate_reading(payload)


def test_non_object_body_is_rejected():
    with pytest.raises(ValidationError):
        services.validate_reading([1, 2, 3])
    with pytest.raises(ValidationError):
        services.validate_reading(None)
