# AGENTS.md

Entry point for every coding agent (and human) working in this repository. Keep this file short; details live in the
modular docs linked below. **Read the linked doc for your task before you change code.**

## Project in one paragraph

Predictive Maintenance Hub: Flask API + vanilla-JS UI + PostgreSQL/SQLite. Operators register machines and submit sensor
readings; the system scores risk, opens work orders, and watches its own key journey (`POST /api/readings`) with
traces/logs/metrics and a user-impact alert. An on-call agent repairs bad config pushes. Spec: [product-spec.md](product-spec.md).

## Modular docs (read what you need)

| Topic | Doc |
|---|---|
| How we work: spec &rarr; issue &rarr; branch &rarr; PR &rarr; CI | [docs/process/workflow.md](docs/process/workflow.md) |
| Task tracker rules, acceptance criteria, evidence | [docs/process/tracker.md](docs/process/tracker.md) |
| Definition of done, testing rules | [docs/process/definition-of-done.md](docs/process/definition-of-done.md) |
| Agent roles and hand-offs | [docs/agent-team.md](docs/agent-team.md), role cards in [agents/roles/](agents/roles) |
| Architecture, data model, risk model | [docs/architecture.md](docs/architecture.md), [docs/adr/](docs/adr) |
| Observability rules (what may enter telemetry) | [docs/observability.md](docs/observability.md) |
| On-call agent, guardrails, permissions | [docs/oncall-agent.md](docs/oncall-agent.md), [docs/permissions.md](docs/permissions.md) |
| Deploy, rollback | [docs/deployment.md](docs/deployment.md) |
| Runbooks | [docs/runbooks/](docs/runbooks) |
| API contract (source of truth) | [openapi.yaml](openapi.yaml) |

## Commands

```bash
make install     # dev dependencies
make dev         # run locally (SQLite + demo data) on :8000
make test        # ALL tests: pytest (unit+integration+on-call) and node --test (frontend)
make up          # docker compose: db + app + alerter + responder
```

## Hard rules

1. **Contract first.** Change `openapi.yaml` in the same PR as any route or response change; `test_openapi_contract.py` must pass.
2. **Tests with every change.** Unit tests for pure logic, integration tests for behaviour that crosses the API/DB.
3. **Never put secrets, tokens, e-mails or assignee names in logs, spans or metrics.** Use `telemetry.log`/`telemetry.span`; they sanitise.
4. **SQL is parameterised** and portable across SQLite and PostgreSQL (`?` placeholders, no vendor-only syntax).
5. **Frontend:** all HTTP goes through `frontend/src/api.js`; set text with `textContent`, never `innerHTML`.
6. **The on-call agent may perform only `config_rollback`.** Do not widen its permissions without an ADR (see [docs/permissions.md](docs/permissions.md)).
7. Do not weaken or delete a failing test to make CI green; fix the cause or open an issue.
8. Work from an issue; reference it in the branch and PR (`Closes #n`).

## Layout

`backend/app` (routes, services, risk, telemetry, db) &middot; `frontend/` &middot; `oncall/` (rules, alerter, responder) &middot;
`ops/alerts` &middot; `scripts/` &middot; `docs/` &middot; `.github/workflows`.
