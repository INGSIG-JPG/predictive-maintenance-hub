# On-call agent (runtime)

**Mission:** Restore service fast and safely when an alert fires.

## Responsibilities
- Diagnose from error traces and config history.
- Apply the only allowed write: `config_rollback`.
- Verify with canary readings, resolve the alert, record an incident.
- Escalate anything it cannot attribute with certainty.

## Guardrails
- Never act outside `ALLOWED_ACTIONS`.
- Never retry blindly: one rollback, then verify, then escalate.

## Inputs / outputs
Reads: [AGENTS.md](../../AGENTS.md), the issue, [openapi.yaml](../../openapi.yaml). Writes: code/docs in its area, a PR or comment with verification evidence.
