"""Built-in observability: traces, structured logs and metrics sharing one trace ID.

* Every request gets a W3C ``traceparent`` compatible trace. An incoming header is honoured.
* Spans and structured log records are collected per request, redacted, and stored in the
  database so they can be queried through the API and viewed in the /observability UI.
* ``/metrics`` exposes Prometheus text format derived from the stored spans.
* Telemetry NEVER stores credentials or personal data: everything goes through ``sanitize``.
"""
from __future__ import annotations

import contextvars
import json
import re
import secrets
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
SENSITIVE_KEY_RE = re.compile(
    r"(token|password|passwd|secret|authorization|cookie|api[_-]?key|email|assigned|technician|phone)",
    re.I,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
BEARER_RE = re.compile(r"(?i)bearer\s+\S+")
MAX_STR = 300
REDACTED = "[REDACTED]"
ROOT_SPAN_NAME = "http.request"


def sanitize(value, key=None, depth: int = 0):
    """Return a JSON-safe copy of ``value`` with sensitive keys/values redacted."""
    if depth > 6:
        return "[TRUNCATED]"
    if key is not None and SENSITIVE_KEY_RE.search(str(key)):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): sanitize(v, k, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, None, depth + 1) for v in list(value)[:50]]
    if isinstance(value, str):
        cleaned = BEARER_RE.sub(REDACTED, EMAIL_RE.sub(REDACTED, value))
        return cleaned[:MAX_STR]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize(str(value), None, depth + 1)


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    started_at: float
    start_perf: float
    attributes: dict = field(default_factory=dict)
    status: str = "ok"
    error_message: str | None = None
    duration_ms: float = 0.0
    route: str | None = None
    status_code: int | None = None
    journey: str | None = None


@dataclass
class TraceContext:
    trace_id: str
    remote_parent: str | None = None
    spans: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    stack: list = field(default_factory=list)


_current: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar("pdm_trace", default=None)


def _new_id(nbytes: int) -> str:
    return secrets.token_hex(nbytes)


def parse_traceparent(header: str | None) -> tuple[str, str] | None:
    if not header:
        return None
    match = TRACEPARENT_RE.match(header.strip().lower())
    if not match:
        return None
    trace_id, parent_id = match.group(1), match.group(2)
    if set(trace_id) == {"0"} or set(parent_id) == {"0"}:
        return None
    return trace_id, parent_id


def begin_trace(traceparent: str | None = None) -> TraceContext:
    parsed = parse_traceparent(traceparent)
    ctx = TraceContext(trace_id=parsed[0] if parsed else _new_id(16), remote_parent=parsed[1] if parsed else None)
    _current.set(ctx)
    return ctx


def end_trace() -> None:
    _current.set(None)


def current() -> TraceContext | None:
    return _current.get()


def current_trace_id() -> str | None:
    ctx = _current.get()
    return ctx.trace_id if ctx else None


def current_span_id() -> str | None:
    ctx = _current.get()
    return ctx.stack[-1].span_id if ctx and ctx.stack else None


def start_span(name: str, attributes: dict | None = None) -> Span | None:
    ctx = _current.get()
    if ctx is None:
        return None
    parent = ctx.stack[-1].span_id if ctx.stack else ctx.remote_parent
    span = Span(
        trace_id=ctx.trace_id,
        span_id=_new_id(8),
        parent_span_id=parent,
        name=name,
        started_at=time.time(),
        start_perf=time.perf_counter(),
        attributes=dict(attributes or {}),
    )
    ctx.stack.append(span)
    return span


def end_span(span: Span | None, error: BaseException | str | None = None) -> None:
    ctx = _current.get()
    if span is None or ctx is None:
        return
    span.duration_ms = round((time.perf_counter() - span.start_perf) * 1000, 3)
    if error is not None:
        span.status = "error"
        if isinstance(error, BaseException):
            span.error_message = sanitize(f"{type(error).__name__}: {error}")
        else:
            span.error_message = sanitize(str(error))
    if span in ctx.stack:
        ctx.stack.remove(span)
    ctx.spans.append(span)


@contextmanager
def span(name: str, **attributes):
    s = start_span(name, attributes)
    try:
        yield s
    except BaseException as exc:
        end_span(s, error=exc)
        raise
    else:
        end_span(s)


def log(level: str, message: str, **fields) -> None:
    """Emit one structured JSON log line and keep it for storage with the trace."""
    ctx = _current.get()
    record = {
        "ts": round(time.time(), 6),
        "level": level.lower(),
        "message": message,
        "trace_id": ctx.trace_id if ctx else None,
        "span_id": current_span_id(),
        "fields": sanitize(fields),
    }
    sys.stdout.write(json.dumps({**{k: record[k] for k in ("ts", "level", "message", "trace_id", "span_id")}, **record["fields"]}) + "\n")
    sys.stdout.flush()
    if ctx is not None:
        ctx.logs.append(record)


# ----------------------------------------------------------------------------- storage

_flushes = 0


def flush(conn, ctx: TraceContext, retention_hours: int = 24) -> None:
    """Persist the spans and logs collected for one request."""
    global _flushes
    for s in ctx.spans:
        conn.execute(
            "INSERT INTO telemetry_spans (trace_id, span_id, parent_span_id, name, started_at, duration_ms,"
            " status, error_message, attributes, route, status_code, journey) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                s.trace_id, s.span_id, s.parent_span_id, s.name, s.started_at, s.duration_ms, s.status,
                s.error_message, json.dumps(sanitize(s.attributes)), s.route, s.status_code, s.journey,
            ),
        )
    for rec in ctx.logs:
        conn.execute(
            "INSERT INTO telemetry_logs (ts, level, message, trace_id, span_id, fields) VALUES (?,?,?,?,?,?)",
            (rec["ts"], rec["level"], rec["message"], rec["trace_id"], rec["span_id"], json.dumps(rec["fields"])),
        )
    _flushes += 1
    if _flushes % 200 == 0:
        prune(conn, retention_hours)
    conn.commit()


def prune(conn, retention_hours: int) -> None:
    cutoff = time.time() - retention_hours * 3600
    conn.execute("DELETE FROM telemetry_spans WHERE started_at < ?", (cutoff,))
    conn.execute("DELETE FROM telemetry_logs WHERE ts < ?", (cutoff,))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, int(-(-pct / 100 * len(ordered) // 1)))  # ceil, nearest-rank
    return round(ordered[min(rank, len(ordered)) - 1], 3)


def summary(conn, window_seconds: int = 300, after: float | None = None) -> dict:
    now = time.time()
    since = max(now - window_seconds, after or 0.0)
    rows = conn.query(
        "SELECT journey, status_code, duration_ms FROM telemetry_spans WHERE name = ? AND started_at >= ?",
        (ROOT_SPAN_NAME, since),
    )
    journeys: dict[str, dict] = {}
    for row in rows:
        if not row["journey"]:
            continue
        j = journeys.setdefault(row["journey"], {"durations": [], "errors": 0})
        j["durations"].append(row["duration_ms"])
        if (row["status_code"] or 0) >= 500:
            j["errors"] += 1
    out = {}
    for name, j in journeys.items():
        n = len(j["durations"])
        out[name] = {
            "requests": n,
            "errors": j["errors"],
            "error_ratio": round(j["errors"] / n, 4) if n else 0.0,
            "p50_ms": _percentile(j["durations"], 50),
            "p95_ms": _percentile(j["durations"], 95),
        }
    return {
        "window_seconds": window_seconds,
        "generated_at": round(now, 3),
        "total_requests": len(rows),
        "journeys": out,
    }


def list_traces(conn, status: str | None = None, journey: str | None = None, limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 100))
    sql = (
        "SELECT r.trace_id, r.started_at, r.duration_ms, r.status, r.route, r.status_code, r.journey,"
        " (SELECT c.error_message FROM telemetry_spans c WHERE c.trace_id = r.trace_id"
        "  AND c.error_message IS NOT NULL ORDER BY c.id LIMIT 1) AS error_message"
        " FROM telemetry_spans r WHERE r.name = ?"
    )
    params: list = [ROOT_SPAN_NAME]
    if status:
        sql += " AND r.status = ?"
        params.append(status)
    if journey:
        sql += " AND r.journey = ?"
        params.append(journey)
    sql += " ORDER BY r.started_at DESC LIMIT ?"
    params.append(limit)
    return conn.query(sql, params)


def get_trace(conn, trace_id: str) -> dict | None:
    spans = conn.query(
        "SELECT span_id, parent_span_id, name, started_at, duration_ms, status, error_message, attributes"
        " FROM telemetry_spans WHERE trace_id = ? ORDER BY started_at, id",
        (trace_id,),
    )
    if not spans:
        return None
    for s in spans:
        s["attributes"] = json.loads(s["attributes"])
    logs = conn.query(
        "SELECT ts, level, message, span_id, fields FROM telemetry_logs WHERE trace_id = ? ORDER BY ts, id",
        (trace_id,),
    )
    for rec in logs:
        rec["fields"] = json.loads(rec["fields"])
    return {"trace_id": trace_id, "spans": spans, "logs": logs}


def _label(value) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def prometheus_text(conn, extra_gauges: dict[str, float] | None = None) -> str:
    lines = [
        "# HELP pdm_http_requests Requests handled, per route and status, within the retention window.",
        "# TYPE pdm_http_requests gauge",
    ]
    rows = conn.query(
        "SELECT route, status_code, COUNT(*) AS c FROM telemetry_spans WHERE name = ?"
        " GROUP BY route, status_code ORDER BY route, status_code",
        (ROOT_SPAN_NAME,),
    )
    for r in rows:
        lines.append(f'pdm_http_requests{{route="{_label(r["route"])}",status="{r["status_code"]}"}} {r["c"]}')
    snap = summary(conn, window_seconds=300)
    lines += [
        "# HELP pdm_journey_error_ratio Share of 5xx responses for a user journey (last 5 minutes).",
        "# TYPE pdm_journey_error_ratio gauge",
    ]
    for name, j in snap["journeys"].items():
        lines.append(f'pdm_journey_error_ratio{{journey="{_label(name)}"}} {j["error_ratio"]}')
    lines += [
        "# HELP pdm_journey_latency_p95_ms 95th percentile latency of a user journey (last 5 minutes).",
        "# TYPE pdm_journey_latency_p95_ms gauge",
    ]
    for name, j in snap["journeys"].items():
        lines.append(f'pdm_journey_latency_p95_ms{{journey="{_label(name)}"}} {j["p95_ms"]}')
    for name, value in (extra_gauges or {}).items():
        lines += [f"# TYPE {name} gauge", f"{name} {value}"]
    return "\n".join(lines) + "\n"
