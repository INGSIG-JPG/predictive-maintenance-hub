"""Shared test data and helpers (imported explicitly by tests)."""

NORMAL = {"temperature_c": 45.0, "vibration_mm_s": 1.2, "pressure_bar": 6.0}
CRITICAL = {"temperature_c": 105.0, "vibration_mm_s": 14.0, "pressure_bar": 9.5}


def post_reading(client, code, values=None, **extra):
    return client.post("/api/readings", json={"machine_code": code, **(values or NORMAL), **extra})
