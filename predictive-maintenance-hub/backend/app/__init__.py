"""Application factory: wires config, database, telemetry hooks, error handlers and routes."""
from __future__ import annotations

import time

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from . import services, telemetry
from .config import Config
from .db import Database
from .errors import AppError
from .routes import bp

SKIP_TELEMETRY_PREFIXES = ("/api/telemetry", "/metrics", "/health", "/ready", "/static")
SKIP_TELEMETRY_PATHS = {"/", "/observability"}


def create_app(config: Config | None = None) -> Flask:
    cfg = config or Config.from_env()
    cfg.validate()
    app = Flask(__name__, static_folder=None)
    app.config["PDM"] = cfg
    app.json.sort_keys = False

    db = Database(cfg.database_url)
    db.init_schema()
    with db.session() as conn:
        services.seed_defaults(conn)
        if cfg.seed_demo_data:
            from .demo import seed_demo

            seed_demo(conn)
    app.extensions["pdm_db"] = db

    @app.before_request
    def _begin():
        g.record_telemetry = not (request.path in SKIP_TELEMETRY_PATHS or request.path.startswith(SKIP_TELEMETRY_PREFIXES))
        g.ctx = telemetry.begin_trace(request.headers.get("traceparent"))
        g.root_span = telemetry.start_span(
            telemetry.ROOT_SPAN_NAME, {"method": request.method, "path": request.path}
        )
        g.journey = None
        g.status_code = None
        g.error_summary = None
        g.t0 = time.perf_counter()
        g.conn = db.connect()

    @app.after_request
    def _after(response):
        ctx = getattr(g, "ctx", None)
        if ctx is not None:
            g.status_code = response.status_code
            response.headers["X-Trace-Id"] = ctx.trace_id
            span_id = g.root_span.span_id if g.root_span else "0" * 16
            response.headers["traceparent"] = f"00-{ctx.trace_id}-{span_id}-01"
        return response

    @app.teardown_request
    def _teardown(exc):
        ctx = getattr(g, "ctx", None)
        if ctx is None:
            return
        conn = getattr(g, "conn", None)
        if conn is not None:
            conn.rollback()  # no-op after commit; frees locks after a failure
            conn.close()
        try:
            root = g.root_span
            status_code = g.status_code or (500 if exc else 0)
            failed = exc is not None or status_code >= 500
            root.route = request.url_rule.rule if request.url_rule else "unmatched"
            root.status_code = status_code
            root.journey = g.journey
            root.attributes.update({"route": root.route, "status_code": status_code})
            if g.journey:
                root.attributes["journey"] = g.journey
            duration_ms = round((time.perf_counter() - g.t0) * 1000, 3)
            telemetry.log(
                "error" if failed else "info", "http_request",
                method=request.method, route=root.route, status_code=status_code,
                duration_ms=duration_ms, journey=g.journey,
            )
            telemetry.end_span(root, error=(exc or g.error_summary or f"HTTP {status_code}") if failed else None)
            if g.record_telemetry:
                with db.session() as tconn:
                    telemetry.flush(tconn, ctx, cfg.telemetry_retention_hours)
        except Exception as flush_error:  # noqa: BLE001 - telemetry must never break a request
            import sys

            print(f'{{"level":"error","message":"telemetry_flush_failed","error":"{type(flush_error).__name__}"}}', file=sys.stderr)
        finally:
            telemetry.end_trace()

    @app.errorhandler(AppError)
    def _app_error(err: AppError):
        body = {"error": err.code, "message": err.message}
        if err.field:
            body["field"] = err.field
        response = jsonify(body)
        response.status_code = err.status
        if err.status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        response = jsonify({"error": (err.name or "error").lower().replace(" ", "_"), "message": err.description})
        response.status_code = err.code or 500
        return response

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):
        summary = f"{type(err).__name__}: {err}"
        g.error_summary = summary
        telemetry.log("error", "unhandled_exception", error=summary)
        response = jsonify(
            {"error": "internal_error", "message": "Unexpected error", "trace_id": telemetry.current_trace_id()}
        )
        response.status_code = 500
        return response

    app.register_blueprint(bp)
    return app
