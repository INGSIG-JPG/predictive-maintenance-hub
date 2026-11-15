"""Tiny database layer supporting SQLite (default, local/tests) and PostgreSQL (compose/prod).

All SQL in the application is written with ``?`` placeholders and portable syntax; this
module translates placeholders for PostgreSQL and provides dialect specific DDL.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS machines (
        id {pk},
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        machine_type TEXT NOT NULL,
        location TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS readings (
        id {pk},
        machine_id BIGINT NOT NULL REFERENCES machines(id),
        recorded_at TEXT NOT NULL,
        temperature_c DOUBLE PRECISION NOT NULL,
        vibration_mm_s DOUBLE PRECISION NOT NULL,
        pressure_bar DOUBLE PRECISION NOT NULL,
        risk_score DOUBLE PRECISION NOT NULL,
        risk_level TEXT NOT NULL,
        model_version TEXT NOT NULL,
        trace_id TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS work_orders (
        id {pk},
        machine_id BIGINT NOT NULL REFERENCES machines(id),
        reading_id BIGINT REFERENCES readings(id),
        title TEXT NOT NULL,
        priority TEXT NOT NULL,
        status TEXT NOT NULL,
        assigned_to TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        trace_id TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS app_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS config_history (
        id {pk},
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        changed_at TEXT NOT NULL,
        changed_by TEXT NOT NULL,
        verified_good INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS telemetry_spans (
        id {pk},
        trace_id TEXT NOT NULL,
        span_id TEXT NOT NULL,
        parent_span_id TEXT,
        name TEXT NOT NULL,
        started_at DOUBLE PRECISION NOT NULL,
        duration_ms DOUBLE PRECISION NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT,
        attributes TEXT NOT NULL,
        route TEXT,
        status_code INTEGER,
        journey TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS telemetry_logs (
        id {pk},
        ts DOUBLE PRECISION NOT NULL,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        trace_id TEXT,
        span_id TEXT,
        fields TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS alerts (
        id {pk},
        rule TEXT NOT NULL,
        status TEXT NOT NULL,
        severity TEXT NOT NULL,
        summary TEXT NOT NULL,
        details TEXT NOT NULL,
        fired_at TEXT NOT NULL,
        resolved_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS incidents (
        id {pk},
        alert_id BIGINT REFERENCES alerts(id),
        status TEXT NOT NULL,
        summary TEXT NOT NULL,
        actions TEXT NOT NULL,
        trace_ids TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_readings_machine ON readings (machine_id, id)",
    "CREATE INDEX IF NOT EXISTS idx_wo_status ON work_orders (status)",
    "CREATE INDEX IF NOT EXISTS idx_spans_trace ON telemetry_spans (trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_spans_started ON telemetry_spans (started_at)",
    "CREATE INDEX IF NOT EXISTS idx_logs_trace ON telemetry_logs (trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_ts ON telemetry_logs (ts)",
]

# Deleted in this order by tests / reset helpers (children first).
TABLES_CHILD_FIRST = [
    "incidents",
    "alerts",
    "telemetry_logs",
    "telemetry_spans",
    "work_orders",
    "readings",
    "config_history",
    "app_config",
    "machines",
]


class Conn:
    """Thin wrapper over a DB-API connection with dict rows and ``?`` placeholders."""

    def __init__(self, raw: Any, dialect: str):
        self.raw = raw
        self.dialect = dialect

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "postgres" else sql

    def execute(self, sql: str, params: Iterable[Any] = ()):
        cur = self.raw.cursor()
        cur.execute(self._sql(sql), tuple(params))
        return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        cur = self.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Run an INSERT and return the new row id (uses RETURNING, valid in both dialects)."""
        cur = self.execute(sql + " RETURNING id", params)
        row = cur.fetchone()
        return int(row["id"])

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        try:
            self.raw.rollback()
        except Exception:  # pragma: no cover - connection already broken
            pass

    def close(self) -> None:
        try:
            self.raw.close()
        except Exception:  # pragma: no cover
            pass


class Database:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("sqlite:///"):
            self.dialect = "sqlite"
            self.sqlite_path = url[len("sqlite:///"):]
        elif url.startswith(("postgres://", "postgresql://")):
            self.dialect = "postgres"
            self.sqlite_path = ""
        else:
            raise ValueError(f"Unsupported DATABASE_URL scheme: {url.split(':', 1)[0]}")

    def connect(self) -> Conn:
        if self.dialect == "sqlite":
            if self.sqlite_path != ":memory:":
                parent = os.path.dirname(os.path.abspath(self.sqlite_path))
                os.makedirs(parent, exist_ok=True)
            raw = sqlite3.connect(self.sqlite_path, timeout=30)
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA foreign_keys = ON")
            raw.execute("PRAGMA journal_mode = WAL")
            return Conn(raw, "sqlite")
        import psycopg  # imported lazily: only needed for PostgreSQL
        from psycopg.rows import dict_row

        raw = psycopg.connect(self.url, row_factory=dict_row)
        return Conn(raw, "postgres")

    @contextmanager
    def session(self) -> Iterator[Conn]:
        conn = self.connect()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        pk = (
            "INTEGER PRIMARY KEY AUTOINCREMENT"
            if self.dialect == "sqlite"
            else "BIGSERIAL PRIMARY KEY"
        )
        with self.session() as conn:
            if self.dialect == "postgres":
                # Serialize schema creation when several workers start at once.
                conn.execute("SELECT pg_advisory_lock(727274)")
            try:
                for statement in SCHEMA:
                    conn.execute(statement.format(pk=pk))
                conn.commit()
            finally:
                if self.dialect == "postgres":
                    conn.execute("SELECT pg_advisory_unlock(727274)")
                    conn.commit()

    def reset(self) -> None:
        """Delete all rows. Used by tests only."""
        with self.session() as conn:
            for table in TABLES_CHILD_FIRST:
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
