"""Business logic. Every function takes an open ``Conn`` and raises ``AppError`` subclasses."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone

from . import risk, telemetry
from .errors import Conflict, Forbidden, NotFound, ValidationError

MACHINE_TYPES = {"pump", "motor", "compressor", "fan", "conveyor", "other"}
CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,31}$")
WO_STATUSES = ["open", "in_progress", "done"]
WO_TRANSITIONS = {"open": {"in_progress", "done"}, "in_progress": {"done", "open"}, "done": set()}
CANARY_CODE = "CANARY-001"
DEFAULT_CONFIG = {"risk_model": "v2", "auto_work_orders": "true"}
CONFIG_ALLOWED = {"risk_model": set(risk.MODELS), "auto_work_orders": {"true", "false"}}
READING_RANGES = {
    "temperature_c": (-50.0, 500.0),
    "vibration_mm_s": (0.0, 200.0),
    "pressure_bar": (0.0, 400.0),
}
RISK_LEVELS = ["low", "medium", "high", "critical"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_precise() -> str:
    """Microsecond precision. Alert resolution times are compared with span timestamps."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _require_obj(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("A JSON object body is required")
    return payload


def _number(payload: dict, field: str, lo: float, hi: float) -> float:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be a number", field)
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValidationError(f"{field} must be between {lo} and {hi}", field)
    return float(value)


def _string(payload: dict, field: str, max_len: int, required: bool = True) -> str | None:
    value = payload.get(field)
    if value is None:
        if required:
            raise ValidationError(f"{field} is required", field)
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValidationError(f"{field} must be a non-empty string", field)
    if len(value) > max_len:
        raise ValidationError(f"{field} must be at most {max_len} characters", field)
    return value.strip()


# --------------------------------------------------------------------------- config

def seed_defaults(conn) -> None:
    for key, value in DEFAULT_CONFIG.items():
        if conn.query_one("SELECT key FROM app_config WHERE key = ?", (key,)) is None:
            ts = now_iso()
            conn.execute("INSERT INTO app_config (key, value, updated_at) VALUES (?,?,?)", (key, value, ts))
            conn.execute(
                "INSERT INTO config_history (key, value, changed_at, changed_by, verified_good) VALUES (?,?,?,?,1)",
                (key, value, ts, "seed"),
            )
    if conn.query_one("SELECT id FROM machines WHERE code = ?", (CANARY_CODE,)) is None:
        conn.execute(
            "INSERT INTO machines (code, name, machine_type, location, created_at) VALUES (?,?,?,?,?)",
            (CANARY_CODE, "Synthetic canary", "other", "monitoring", now_iso()),
        )
    conn.commit()


def get_config_value(conn, key: str) -> str:
    row = conn.query_one("SELECT value FROM app_config WHERE key = ?", (key,))
    if row is None:
        raise NotFound(f"config key '{key}' not found")
    return row["value"]


def _history_rows(conn, key: str | None = None, limit: int = 20) -> list[dict]:
    if key:
        rows = conn.query("SELECT * FROM config_history WHERE key = ? ORDER BY id DESC LIMIT ?", (key, limit))
    else:
        rows = conn.query("SELECT * FROM config_history ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["verified_good"] = bool(r["verified_good"])
    return rows


def config_state(conn) -> dict:
    values = {r["key"]: r["value"] for r in conn.query("SELECT key, value FROM app_config")}
    verified = {}
    for key, value in values.items():
        latest = conn.query_one("SELECT value, verified_good FROM config_history WHERE key = ? ORDER BY id DESC LIMIT 1", (key,))
        verified[key] = bool(latest and latest["value"] == value and latest["verified_good"])
    return {"values": values, "verified": verified, "history": _history_rows(conn)}


def _write_config(conn, key: str, value: str, actor: str, verified: bool) -> None:
    ts = now_iso()
    conn.execute(
        "INSERT INTO app_config (key, value, updated_at) VALUES (?,?,?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, ts),
    )
    conn.execute(
        "INSERT INTO config_history (key, value, changed_at, changed_by, verified_good) VALUES (?,?,?,?,?)",
        (key, value, ts, actor, 1 if verified else 0),
    )


def set_config(conn, key: str, payload, actor: str, fault_injection_enabled: bool) -> dict:
    payload = _require_obj(payload)
    if key not in CONFIG_ALLOWED:
        raise NotFound(f"config key '{key}' not found")
    value = payload.get("value")
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValidationError("value must be a non-empty string of at most 64 characters", "value")
    skip = payload.get("skip_validation") is True
    if skip and not fault_injection_enabled:
        raise Forbidden("skip_validation is disabled (fault injection is off in this environment)")
    if not skip and value not in CONFIG_ALLOWED[key]:
        raise ValidationError(f"value must be one of {sorted(CONFIG_ALLOWED[key])}", "value")
    previous = get_config_value(conn, key)
    verified = payload.get("verified") is True and not skip
    _write_config(conn, key, value, actor, verified)
    conn.commit()
    telemetry.log("warning", "config_changed", key=key, previous=previous, value=value, actor=actor, validated=not skip)
    return {"key": key, "value": value, "previous": previous, "verified": verified}


def verify_config(conn, key: str, actor: str) -> dict:
    if key not in CONFIG_ALLOWED:
        raise NotFound(f"config key '{key}' not found")
    current = get_config_value(conn, key)
    if current not in CONFIG_ALLOWED[key]:
        raise Conflict(f"current value '{current}' is not valid and cannot be verified")
    _write_config(conn, key, current, actor, True)
    conn.commit()
    return {"key": key, "value": current, "verified": True}


def rollback_config(conn, key: str, actor: str) -> dict:
    if key not in CONFIG_ALLOWED:
        raise NotFound(f"config key '{key}' not found")
    current = get_config_value(conn, key)
    target = conn.query_one(
        "SELECT value FROM config_history WHERE key = ? AND verified_good = 1 AND value <> ? ORDER BY id DESC LIMIT 1",
        (key, current),
    )
    if target is None:
        raise Conflict(f"no known-good value different from '{current}' to roll back to")
    _write_config(conn, key, target["value"], f"rollback:{actor}", True)
    conn.commit()
    telemetry.log("warning", "config_rolled_back", key=key, previous=current, value=target["value"], actor=actor)
    return {"key": key, "from": current, "to": target["value"]}


# --------------------------------------------------------------------------- machines

_MACHINE_SELECT = (
    "SELECT m.id, m.code, m.name, m.machine_type, m.location, m.created_at,"
    " (SELECT r.risk_level FROM readings r WHERE r.machine_id = m.id ORDER BY r.id DESC LIMIT 1) AS latest_risk_level,"
    " (SELECT r.risk_score FROM readings r WHERE r.machine_id = m.id ORDER BY r.id DESC LIMIT 1) AS latest_risk_score,"
    " (SELECT r.recorded_at FROM readings r WHERE r.machine_id = m.id ORDER BY r.id DESC LIMIT 1) AS latest_reading_at"
    " FROM machines m"
)


def create_machine(conn, payload) -> dict:
    payload = _require_obj(payload)
    code = _string(payload, "code", 32)
    if not CODE_RE.match(code):
        raise ValidationError("code must be 3-32 chars: uppercase letters, digits or '-'", "code")
    name = _string(payload, "name", 100)
    machine_type = _string(payload, "machine_type", 20)
    if machine_type not in MACHINE_TYPES:
        raise ValidationError(f"machine_type must be one of {sorted(MACHINE_TYPES)}", "machine_type")
    location = _string(payload, "location", 100, required=False) or ""
    if conn.query_one("SELECT id FROM machines WHERE code = ?", (code,)):
        raise Conflict(f"machine with code '{code}' already exists", "code")
    machine_id = conn.insert(
        "INSERT INTO machines (code, name, machine_type, location, created_at) VALUES (?,?,?,?,?)",
        (code, name, machine_type, location, now_iso()),
    )
    conn.commit()
    telemetry.log("info", "machine_created", machine_id=machine_id, code=code)
    return get_machine(conn, machine_id)


def list_machines(conn) -> list[dict]:
    return conn.query(_MACHINE_SELECT + " WHERE m.code NOT LIKE 'CANARY-%' ORDER BY m.code")


def get_machine(conn, machine_id: int) -> dict:
    row = conn.query_one(_MACHINE_SELECT + " WHERE m.id = ?", (machine_id,))
    if row is None:
        raise NotFound(f"machine {machine_id} not found")
    return row


# --------------------------------------------------------------------------- readings

def _parse_recorded_at(payload: dict) -> str:
    raw = payload.get("recorded_at")
    if raw is None:
        return now_iso()
    if not isinstance(raw, str):
        raise ValidationError("recorded_at must be an ISO-8601 string", "recorded_at")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("recorded_at must be an ISO-8601 string", "recorded_at") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def validate_reading(payload) -> dict:
    payload = _require_obj(payload)
    code = _string(payload, "machine_code", 32)
    values = {f: _number(payload, f, *READING_RANGES[f]) for f in READING_RANGES}
    return {"machine_code": code, "recorded_at": _parse_recorded_at(payload), **values}


def _history(conn, machine_id: int, limit: int = 50) -> dict[str, list[float]]:
    rows = conn.query(
        "SELECT temperature_c, vibration_mm_s, pressure_bar FROM readings WHERE machine_id = ? ORDER BY id DESC LIMIT ?",
        (machine_id, limit),
    )
    return {k: [r[k] for r in rows] for k in READING_RANGES}


def ingest_reading(conn, payload) -> dict:
    """Key user journey: record a sensor reading, score it, open a work order when risky."""
    data = validate_reading(payload)
    machine = conn.query_one("SELECT id, code, name FROM machines WHERE code = ?", (data["machine_code"],))
    if machine is None:
        raise NotFound(f"machine '{data['machine_code']}' not found")
    model = get_config_value(conn, "risk_model")
    values = {k: data[k] for k in READING_RANGES}
    with telemetry.span("risk.score", model=model, machine_id=machine["id"]):
        history = _history(conn, machine["id"]) if risk.needs_history(model) else {}
        result = risk.score_reading(model, values, history)
    with telemetry.span("db.insert_reading", machine_id=machine["id"]):
        reading_id = conn.insert(
            "INSERT INTO readings (machine_id, recorded_at, temperature_c, vibration_mm_s, pressure_bar,"
            " risk_score, risk_level, model_version, trace_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (machine["id"], data["recorded_at"], values["temperature_c"], values["vibration_mm_s"],
             values["pressure_bar"], result.score, result.level, model, telemetry.current_trace_id()),
        )
    work_order_id = None
    if result.level in {"high", "critical"} and get_config_value(conn, "auto_work_orders") == "true":
        existing = conn.query_one(
            "SELECT id FROM work_orders WHERE machine_id = ? AND status <> 'done' ORDER BY id DESC LIMIT 1",
            (machine["id"],),
        )
        if existing is None:
            with telemetry.span("workorder.create", machine_id=machine["id"], level=result.level):
                ts = now_iso()
                work_order_id = conn.insert(
                    "INSERT INTO work_orders (machine_id, reading_id, title, priority, status, assigned_to,"
                    " created_at, updated_at, trace_id) VALUES (?,?,?,?,?,?,?,?,?)",
                    (machine["id"], reading_id,
                     f"Inspect {machine['name']} ({machine['code']}): {result.level} risk ({result.score:.0f})",
                     "P1" if result.level == "critical" else "P2", "open", None, ts, ts,
                     telemetry.current_trace_id()),
                )
        else:
            telemetry.log("info", "work_order_skipped_existing", machine_id=machine["id"], work_order_id=existing["id"])
    conn.commit()
    telemetry.log("info", "reading_ingested", machine_id=machine["id"], reading_id=reading_id,
                  risk_level=result.level, risk_score=result.score, model=model, work_order_id=work_order_id)
    return {
        "reading": get_reading(conn, reading_id),
        "work_order": get_work_order(conn, work_order_id) if work_order_id else None,
    }


def get_reading(conn, reading_id: int) -> dict:
    return conn.query_one("SELECT * FROM readings WHERE id = ?", (reading_id,))


def list_readings(conn, machine_id: int, limit: int = 50) -> list[dict]:
    get_machine(conn, machine_id)
    limit = max(1, min(limit, 500))
    return conn.query("SELECT * FROM readings WHERE machine_id = ? ORDER BY id DESC LIMIT ?", (machine_id, limit))


# --------------------------------------------------------------------------- work orders

_WO_SELECT = (
    "SELECT w.id, w.machine_id, m.code AS machine_code, m.name AS machine_name, w.reading_id, w.title,"
    " w.priority, w.status, w.assigned_to, w.created_at, w.updated_at, w.trace_id"
    " FROM work_orders w JOIN machines m ON m.id = w.machine_id"
)


def get_work_order(conn, work_order_id: int) -> dict:
    row = conn.query_one(_WO_SELECT + " WHERE w.id = ?", (work_order_id,))
    if row is None:
        raise NotFound(f"work order {work_order_id} not found")
    return row


def list_work_orders(conn, status: str | None = None, limit: int = 100) -> list[dict]:
    if status is not None and status not in WO_STATUSES:
        raise ValidationError(f"status must be one of {WO_STATUSES}", "status")
    limit = max(1, min(limit, 500))
    if status:
        return conn.query(_WO_SELECT + " WHERE w.status = ? ORDER BY w.id DESC LIMIT ?", (status, limit))
    return conn.query(_WO_SELECT + " ORDER BY w.id DESC LIMIT ?", (limit,))


def update_work_order(conn, work_order_id: int, payload) -> dict:
    payload = _require_obj(payload)
    current = get_work_order(conn, work_order_id)
    unknown = set(payload) - {"status", "assigned_to"}
    if unknown:
        raise ValidationError(f"unknown field(s): {sorted(unknown)}")
    if not payload:
        raise ValidationError("provide status and/or assigned_to")
    status, assigned = current["status"], current["assigned_to"]
    if "status" in payload:
        new = payload["status"]
        if new not in WO_STATUSES:
            raise ValidationError(f"status must be one of {WO_STATUSES}", "status")
        if new != current["status"] and new not in WO_TRANSITIONS[current["status"]]:
            raise Conflict(f"cannot move work order from '{current['status']}' to '{new}'", "status")
        status = new
    if "assigned_to" in payload:
        assigned = _string(payload, "assigned_to", 100, required=False)
    conn.execute("UPDATE work_orders SET status = ?, assigned_to = ?, updated_at = ? WHERE id = ?",
                 (status, assigned, now_iso(), work_order_id))
    conn.commit()
    telemetry.log("info", "work_order_updated", work_order_id=work_order_id, status=status, assigned_to=assigned)
    return get_work_order(conn, work_order_id)


# --------------------------------------------------------------------------- dashboard

def dashboard_summary(conn) -> dict:
    machines = list_machines(conn)
    by_level = {level: 0 for level in RISK_LEVELS}
    by_level["unknown"] = 0
    for m in machines:
        by_level[m["latest_risk_level"] or "unknown"] += 1
    open_wo = conn.query_one("SELECT COUNT(*) AS c FROM work_orders WHERE status <> 'done'")["c"]
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    readings = conn.query_one(
        "SELECT COUNT(*) AS c FROM readings r JOIN machines m ON m.id = r.machine_id"
        " WHERE r.recorded_at >= ? AND m.code NOT LIKE 'CANARY-%'", (since,))["c"]
    return {
        "machines_total": len(machines),
        "by_risk_level": by_level,
        "open_work_orders": open_wo,
        "readings_24h": readings,
        "risk_model": get_config_value(conn, "risk_model"),
    }


# --------------------------------------------------------------------------- alerts & incidents

def _decode(row: dict, *fields: str) -> dict:
    for f in fields:
        row[f] = json.loads(row[f])
    return row


def create_alert(conn, payload) -> dict:
    payload = _require_obj(payload)
    rule = _string(payload, "rule", 100)
    severity = _string(payload, "severity", 20)
    if severity not in {"info", "warning", "critical"}:
        raise ValidationError("severity must be info, warning or critical", "severity")
    summary = _string(payload, "summary", 300)
    details = payload.get("details", {})
    if not isinstance(details, dict):
        raise ValidationError("details must be an object", "details")
    alert_id = conn.insert(
        "INSERT INTO alerts (rule, status, severity, summary, details, fired_at) VALUES (?,?,?,?,?,?)",
        (rule, "firing", severity, summary, json.dumps(telemetry.sanitize(details)), now_iso()),
    )
    conn.commit()
    telemetry.log("error", "alert_fired", alert_id=alert_id, rule=rule, severity=severity)
    return get_alert(conn, alert_id)


def get_alert(conn, alert_id: int) -> dict:
    row = conn.query_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    if row is None:
        raise NotFound(f"alert {alert_id} not found")
    return _decode(row, "details")


def list_alerts(conn, status: str | None = None, rule: str | None = None, limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 200))
    sql, params = "SELECT * FROM alerts WHERE 1=1", []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if rule:
        sql += " AND rule = ?"
        params.append(rule)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [_decode(r, "details") for r in conn.query(sql, params)]


def resolve_alert(conn, alert_id: int, payload) -> dict:
    payload = _require_obj(payload)
    if payload.get("status") != "resolved":
        raise ValidationError("status must be 'resolved'", "status")
    alert = get_alert(conn, alert_id)
    if alert["status"] != "resolved":
        conn.execute("UPDATE alerts SET status = 'resolved', resolved_at = ? WHERE id = ?", (now_precise(), alert_id))
        conn.commit()
        telemetry.log("info", "alert_resolved", alert_id=alert_id, rule=alert["rule"])
    return get_alert(conn, alert_id)


def create_incident(conn, payload) -> dict:
    payload = _require_obj(payload)
    status = _string(payload, "status", 20)
    if status not in {"resolved", "escalated", "dry_run"}:
        raise ValidationError("status must be resolved, escalated or dry_run", "status")
    summary = _string(payload, "summary", 1000)
    actions, trace_ids = payload.get("actions", []), payload.get("trace_ids", [])
    if not isinstance(actions, list) or not all(isinstance(a, dict) for a in actions):
        raise ValidationError("actions must be a list of objects", "actions")
    if not isinstance(trace_ids, list) or not all(isinstance(t, str) for t in trace_ids):
        raise ValidationError("trace_ids must be a list of strings", "trace_ids")
    alert_id = payload.get("alert_id")
    if alert_id is not None:
        if isinstance(alert_id, bool) or not isinstance(alert_id, int):
            raise ValidationError("alert_id must be an integer", "alert_id")
        get_alert(conn, alert_id)
    incident_id = conn.insert(
        "INSERT INTO incidents (alert_id, status, summary, actions, trace_ids, created_at) VALUES (?,?,?,?,?,?)",
        (alert_id, status, summary, json.dumps(telemetry.sanitize(actions)), json.dumps(trace_ids[:50]), now_iso()),
    )
    conn.commit()
    telemetry.log("info", "incident_recorded", incident_id=incident_id, status=status, alert_id=alert_id)
    return _decode(conn.query_one("SELECT * FROM incidents WHERE id = ?", (incident_id,)), "actions", "trace_ids")


def list_incidents(conn, limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 200))
    rows = conn.query("SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,))
    return [_decode(r, "actions", "trace_ids") for r in rows]
