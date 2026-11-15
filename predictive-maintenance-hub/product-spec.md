# Product Specification - Predictive Maintenance Hub

Status: v1.0. This document was written **before** implementation; each requirement maps to a GitHub issue
(see [docs/tracker](docs/tracker)) and to automated tests.

## 1. Goal and users

Help maintenance teams decide which machines to inspect first, and keep the data pipeline trustworthy.

| User | Needs |
|---|---|
| Maintenance planner | See fleet risk at a glance; get a work order when a machine degrades |
| Technician | Pick up, progress and close work orders |
| Reliability / on-call engineer | Know within minutes when recording readings is failing, and have it recover |

Out of scope for v1: end-user authentication, multi-tenant data, real-time streaming protocols (MQTT/OPC UA), trained ML models.

## 2. Functional requirements

Priority: **M** must, **S** should.

| ID | Req | Pri | Acceptance criteria (Given / When / Then) |
|---|---|---|---|
| FR-1 | Register a machine | M | Given a unique code `[A-Z0-9-]{3,32}`, name and type, when I POST `/api/machines`, then I get `201` and the machine appears in the list. A duplicate code returns `409`; invalid input returns `422` with the failing `field`. |
| FR-2 | Record a reading | M | Given a registered machine, when I POST temperature, vibration, pressure, then the reading is stored with a risk score 0-100 and level, and the response carries `X-Trace-Id`. Unknown machine &rarr; `404`; out-of-range or non-numeric values &rarr; `422`. |
| FR-3 | Risk scoring | M | `v1`: normal values score `low`; every limit exceeded scores `100`/`critical`; boundaries 40/70/85. `v2`: adds up to +15 when a value is a statistical outlier versus the machine's last 50 readings (needs &ge;10). Score never exceeds 100. |
| FR-4 | Automatic work orders | M | A `high` reading opens a `P2` work order; `critical` opens `P1`. If the machine has a non-done work order, none is created. Can be disabled with config `auto_work_orders=false`. |
| FR-5 | Work-order workflow | M | `open`&rarr;`in_progress`&rarr;`done`; `done` is final (`409` otherwise); assignee can be set; unknown fields &rarr; `422`. |
| FR-6 | Dashboard | M | Shows machine count, counts per risk level, open work orders, readings in 24 h, active risk model; machines table with latest risk; forms for FR-1/FR-2; work-order actions. Data persists across restarts. |
| FR-7 | Reading history | S | `GET /api/machines/{id}/readings` returns the newest first, `limit` 1-500. |
| FR-8 | Runtime configuration | M | Admin can change `risk_model` and `auto_work_orders`; invalid values are rejected (`422`); every change is recorded with actor and "verified" flag; the latest verified-good value can be restored (`rollback`). |

## 3. Non-functional requirements

| ID | Req | Acceptance criteria |
|---|---|---|
| NFR-1 | Contract | `openapi.yaml` lists every route; a contract test fails when routes or response shapes drift. |
| NFR-2 | Observability | The key journey (FR-2) emits a root span, child spans, structured logs and metrics sharing one trace ID, collected and viewable in the UI at `/observability`. No credentials or customer data are stored in telemetry. |
| NFR-3 | Alerting on user impact | At least one alert is based on the journey's error ratio or latency, not on CPU or memory. |
| NFR-4 | Self-healing | When a bad config breaks FR-2, an on-call agent wakes on the alert, restores service, verifies it, resolves the alert and records an incident, with no human action. |
| NFR-5 | Single-command operation | `docker compose up --build` starts database, app, alerter and agent; `make test` runs all tests. |
| NFR-6 | Delivery | CI on every PR; automatic deploy to dev after green CI on `main`; manual deploy to production with approval; rollback by redeploying a previous ref. |
| NFR-7 | Security | Admin endpoints need a bearer token (constant-time comparison); production refuses to start with the default token; fault injection is off in production; UI renders API data with `textContent` only; all SQL is parameterised. |

## 4. Key user journey (instrumented)

`POST /api/readings`: validate &rarr; load config &rarr; **risk.score** &rarr; **db.insert_reading** &rarr; (maybe) **workorder.create** &rarr; respond.

## 5. Alert rules

| Rule | Condition | Severity | Responder |
|---|---|---|---|
| `ingest_reading_error_rate` | error ratio > 5 % over 120 s, &ge;5 requests | critical | on-call agent (auto-fix) |
| `ingest_reading_latency_p95` | p95 > 1500 ms over 180 s, &ge;10 requests | warning | escalate to a human (no safe automated fix) |

## 6. Incident scenario used to verify NFR-4

An operator pushes an unvalidated `risk_model` value (fault injection): every reading fails with `500`. Expected: alert fires,
the agent rolls back to the last verified value, three canary readings succeed, alert resolves, incident `resolved` is stored
with the failing trace IDs. Covered by `oncall/tests/test_oncall_e2e.py` and `make incident`.

## 7. Traceability

Requirement &rarr; issue &rarr; tests: see [docs/tracker/README.md](docs/tracker/README.md).
