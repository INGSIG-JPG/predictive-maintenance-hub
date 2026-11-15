# Architecture

## Components

* **API + UI server** (`backend/app`): Flask app created by `create_app()`. Layers: `routes.py` (HTTP, thin) &rarr;
  `services.py` (business rules, validation) &rarr; `db.py` (portable SQL). `risk.py` is pure logic. `telemetry.py` is the observability core.
* **Frontend** (`frontend/`): static ES modules served by the same server (`/`, `/observability`, `/static/...`).
* **Alerter** (`oncall/alerter.py`): evaluates [alert rules](../ops/alerts/alert-rules.yaml) against `/api/telemetry/summary`; fires alerts; wakes the agent.
* **On-call agent** (`oncall/responder.py`): webhook server running the incident runbook ([design](oncall-agent.md)).

## Request lifecycle and telemetry

`before_request` starts a trace (honouring an incoming W3C `traceparent`) and a root span `http.request`. Services add child
spans with `telemetry.span(...)` and structured logs with `telemetry.log(...)`. In `teardown_request` the root span is closed
with route, status code and *journey*, and spans plus logs are written to the database in one transaction. Responses carry
`X-Trace-Id` and `traceparent`. Operational endpoints (`/health`, `/ready`, `/metrics`, static pages, telemetry reads) are not recorded,
so observing the system does not pollute what is observed.

## Data model

| Table | Purpose |
|---|---|
| `machines` | Registered equipment (unique `code`). `CANARY-001` is a hidden synthetic machine used for health probes. |
| `readings` | Sensor values, `risk_score`, `risk_level`, `model_version`, `trace_id` |
| `work_orders` | Maintenance tasks created from risky readings; status workflow; links to reading and trace |
| `app_config` / `config_history` | Runtime config and an audit trail with a `verified_good` flag (rollback target) |
| `telemetry_spans` / `telemetry_logs` | Collected traces and structured logs (24 h retention) |
| `alerts` / `incidents` | Fired alerts and the on-call agent's reports |

Environments: `DATABASE_URL=sqlite:///...` (local, tests) or `postgresql://...` (compose, deployment). The schema is created idempotently at startup.

## Risk model

Each signal is ramped between a warning and a critical limit (temperature 60-95 &deg;C, vibration 2.8-11.2 mm/s, pressure deviation
1-3 bar from a 6 bar nominal). Score = `100 * (0.6 * worst + 0.4 * weighted mean)` with weights 0.35 / 0.45 / 0.20. Levels:
&ge;85 critical, &ge;70 high, &ge;40 medium. `v2` adds up to +15 for z-score outliers against the machine's last 50 readings
(needs 10). The limits are illustrative defaults and must be calibrated per machine class before real use.

## Decisions

[ADR-001 Flask + SQL](adr/001-flask-and-portable-sql.md) &middot; [ADR-002 Contract first](adr/002-contract-first.md) &middot;
[ADR-003 Built-in telemetry](adr/003-builtin-telemetry.md) &middot; [ADR-004 Runbook agent](adr/004-runbook-agent.md)
