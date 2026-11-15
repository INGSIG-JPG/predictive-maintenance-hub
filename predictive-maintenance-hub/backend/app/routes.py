"""HTTP layer. Thin: parse input, call services, shape JSON. Contract lives in openapi.yaml."""
from __future__ import annotations

import hmac
from functools import wraps

from flask import Blueprint, Response, current_app, g, jsonify, request, send_from_directory

from . import services, telemetry
from .errors import NotFound, Unauthorized, ValidationError

bp = Blueprint("api", __name__)


def _cfg():
    return current_app.config["PDM"]


def _conn():
    return g.conn


def _int_arg(name: str, default: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValidationError(f"{name} must be an integer", name) from None


def _json_body():
    return request.get_json(silent=True)


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else ""
        if not token or not hmac.compare_digest(token.encode(), _cfg().admin_token.encode()):
            raise Unauthorized("a valid admin bearer token is required")
        return fn(*args, **kwargs)

    return wrapper


# ------------------------------------------------------------------ operational

@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/ready")
def ready():
    try:
        _conn().query_one("SELECT 1 AS ok")
    except Exception:  # noqa: BLE001 - readiness must never raise
        return jsonify({"status": "unavailable"}), 503
    return jsonify({"status": "ready"})


@bp.get("/metrics")
def metrics():
    conn = _conn()
    extra = {
        "pdm_open_work_orders": conn.query_one("SELECT COUNT(*) AS c FROM work_orders WHERE status <> 'done'")["c"],
        "pdm_machines": conn.query_one("SELECT COUNT(*) AS c FROM machines")["c"],
    }
    return Response(telemetry.prometheus_text(conn, extra), mimetype="text/plain; version=0.0.4")


# ------------------------------------------------------------------ frontend

@bp.get("/")
def index():
    return send_from_directory(_cfg().frontend_dir, "index.html")


@bp.get("/observability")
def observability_page():
    return send_from_directory(_cfg().frontend_dir, "observability.html")


@bp.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(_cfg().frontend_dir, filename)


# ------------------------------------------------------------------ machines & readings

@bp.get("/api/dashboard/summary")
def dashboard():
    return jsonify(services.dashboard_summary(_conn()))


@bp.get("/api/machines")
def machines_list():
    return jsonify({"items": services.list_machines(_conn())})


@bp.post("/api/machines")
def machines_create():
    return jsonify(services.create_machine(_conn(), _json_body())), 201


@bp.get("/api/machines/<int:machine_id>")
def machines_get(machine_id):
    return jsonify(services.get_machine(_conn(), machine_id))


@bp.get("/api/machines/<int:machine_id>/readings")
def machine_readings(machine_id):
    return jsonify({"items": services.list_readings(_conn(), machine_id, _int_arg("limit", 50))})


@bp.post("/api/readings")
def readings_create():
    g.journey = "ingest_reading"
    return jsonify(services.ingest_reading(_conn(), _json_body())), 201


# ------------------------------------------------------------------ work orders

@bp.get("/api/work-orders")
def work_orders_list():
    return jsonify({"items": services.list_work_orders(_conn(), request.args.get("status"), _int_arg("limit", 100))})


@bp.patch("/api/work-orders/<int:work_order_id>")
def work_orders_patch(work_order_id):
    return jsonify(services.update_work_order(_conn(), work_order_id, _json_body()))


# ------------------------------------------------------------------ telemetry

@bp.get("/api/telemetry/summary")
def telemetry_summary():
    after = request.args.get("after")
    try:
        after_value = float(after) if after else None
    except ValueError:
        raise ValidationError("after must be a unix timestamp", "after") from None
    window = max(10, min(_int_arg("window", 300), 3600))
    return jsonify(telemetry.summary(_conn(), window, after_value))


@bp.get("/api/telemetry/traces")
def telemetry_traces():
    items = telemetry.list_traces(
        _conn(), request.args.get("status"), request.args.get("journey"), _int_arg("limit", 20)
    )
    return jsonify({"items": items})


@bp.get("/api/telemetry/traces/<trace_id>")
def telemetry_trace(trace_id):
    trace = telemetry.get_trace(_conn(), trace_id)
    if trace is None:
        raise NotFound(f"trace '{trace_id}' not found")
    return jsonify(trace)


# ------------------------------------------------------------------ alerts & incidents

@bp.get("/api/alerts")
def alerts_list():
    items = services.list_alerts(_conn(), request.args.get("status"), request.args.get("rule"), _int_arg("limit", 50))
    return jsonify({"items": items})


@bp.post("/api/alerts")
@require_admin
def alerts_create():
    return jsonify(services.create_alert(_conn(), _json_body())), 201


@bp.patch("/api/alerts/<int:alert_id>")
@require_admin
def alerts_patch(alert_id):
    return jsonify(services.resolve_alert(_conn(), alert_id, _json_body()))


@bp.get("/api/incidents")
def incidents_list():
    return jsonify({"items": services.list_incidents(_conn(), _int_arg("limit", 50))})


@bp.post("/api/incidents")
@require_admin
def incidents_create():
    return jsonify(services.create_incident(_conn(), _json_body())), 201


# ------------------------------------------------------------------ admin config

@bp.get("/admin/config")
@require_admin
def admin_config():
    return jsonify(services.config_state(_conn()))


@bp.put("/admin/config/<key>")
@require_admin
def admin_config_set(key):
    actor = request.headers.get("X-Actor", "admin")[:40]
    return jsonify(services.set_config(_conn(), key, _json_body(), actor, _cfg().enable_fault_injection))


@bp.post("/admin/config/<key>/rollback")
@require_admin
def admin_config_rollback(key):
    actor = request.headers.get("X-Actor", "admin")[:40]
    return jsonify(services.rollback_config(_conn(), key, actor))


@bp.post("/admin/config/<key>/verify")
@require_admin
def admin_config_verify(key):
    actor = request.headers.get("X-Actor", "admin")[:40]
    return jsonify(services.verify_config(_conn(), key, actor))
