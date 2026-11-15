"""Optional demo data (SEED_DEMO_DATA=true) so a fresh install shows something useful."""
from __future__ import annotations

from . import services

DEMO_MACHINES = [
    ("PUMP-001", "Cooling water pump", "pump", "Plant A"),
    ("MOTOR-014", "Conveyor drive motor", "motor", "Plant A"),
    ("COMP-007", "Air compressor", "compressor", "Plant B"),
    ("FAN-003", "Extraction fan", "fan", "Plant B"),
]


def seed_demo(conn) -> None:
    for code, name, kind, location in DEMO_MACHINES:
        if conn.query_one("SELECT id FROM machines WHERE code = ?", (code,)) is None:
            services.create_machine(conn, {"code": code, "name": name, "machine_type": kind, "location": location})
