# Observability

## Key user journey: record a reading (`POST /api/readings`)

| Signal | What | Where to see it |
|---|---|---|
| Trace | root span `http.request` + `risk.score`, `db.insert_reading`, `workorder.create` | `/observability` &rarr; click a trace |
| Structured logs | JSON lines on stdout (also stored), each with `trace_id` and `span_id` | same trace view, and container logs |
| Metrics | `pdm_http_requests`, `pdm_journey_error_ratio`, `pdm_journey_latency_p95_ms`, `pdm_open_work_orders` | `/metrics` (Prometheus text), journey tiles in the UI |

All three share the **trace ID**, returned in the `X-Trace-Id` response header and stored on readings and work orders,
so a user report ("this reading failed") maps to exactly one trace.

## What must never reach telemetry

Credentials and customer data. `telemetry.sanitize` redacts any key matching token, password, secret, authorization, cookie,
api key, e-mail, phone, assigned, technician, redacts values that look like e-mails or bearer tokens, and truncates strings to 300
characters. Verified by `test_no_customer_data_or_credentials_reach_telemetry`. When adding a field to a log or span, add it to that test.

## Alerts

[`ops/alerts/alert-rules.yaml`](../ops/alerts/alert-rules.yaml): error ratio and p95 latency of the journey. They describe what
users feel. CPU and memory graphs are deliberately not alert sources.

## Retention

24 h by default (`TELEMETRY_RETENTION_HOURS`), pruned periodically.
