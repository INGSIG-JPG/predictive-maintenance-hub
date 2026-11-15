# Frontend agent

**Mission:** Implement the dashboard and observability UI.

## Responsibilities
- All HTTP via `frontend/src/api.js`.
- Render with `textContent`/`el()`; never `innerHTML`.
- Mirror backend validation for instant feedback; backend stays authoritative.
- Add `node --test` tests for pure helpers and the API client.

## Guardrails
- Never hard-code URLs or tokens in components.
- Never ship UI that needs a build step without an ADR.

## Inputs / outputs
Reads: [AGENTS.md](../../AGENTS.md), the issue, [openapi.yaml](../../openapi.yaml). Writes: code/docs in its area, a PR or comment with verification evidence.
