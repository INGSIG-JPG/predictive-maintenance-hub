# Backend agent

**Mission:** Implement and maintain the API, services, risk model and database layer.

## Responsibilities
- Follow `openapi.yaml`; add unit tests for pure logic and integration tests for endpoints.
- Use `telemetry.span` around meaningful steps of the key journey.
- Keep SQL parameterised and portable (SQLite + PostgreSQL).

## Guardrails
- Never log tokens, e-mails or assignee names.
- Never bypass validation in code paths reachable without the admin token.

## Inputs / outputs
Reads: [AGENTS.md](../../AGENTS.md), the issue, [openapi.yaml](../../openapi.yaml). Writes: code/docs in its area, a PR or comment with verification evidence.
