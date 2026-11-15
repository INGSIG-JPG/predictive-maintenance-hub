# On-call agent

## Trigger

`python -m oncall.alerter` evaluates the rules every `ALERT_INTERVAL_SECONDS`. When a rule breaches (with enough traffic to judge)
and no alert for it is firing, it creates an alert (`POST /api/alerts`) and calls the responder webhook
(`POST /alert`, header `X-Webhook-Secret`).

## Runbook executed by `oncall/responder.py`

1. **Diagnose.** Read recent error traces of the journey and the config state. Cause `bad_risk_model_config` only if most errors
   mention an unknown risk model **and** the current value is not verified-good.
2. **Act.** `POST /admin/config/risk_model/rollback` restores the latest verified-good value.
3. **Verify.** Three consecutive canary readings (`CANARY-001`) must return `201`.
4. **Close.** Mark the restored value verified, resolve the alert, record an incident (summary, actions, failing trace IDs).
5. **Escalate** otherwise: record an `escalated` incident with the reason; the alert stays firing for a human.

After a resolution the alerter ignores spans older than the resolution time, so an old incident cannot re-fire.

## Guardrails

* The only allowed write is `config_rollback` (`ALLOWED_ACTIONS`; a test proves other actions raise `PermissionError`).
* `RESPONDER_DRY_RUN=true` records what it *would* do without doing it.
* Latency alerts have `responder: escalate`: no safe automated fix exists, so a human is told.
* One incident at a time (lock); webhook requires a shared secret (constant-time comparison); no secret ever enters telemetry.
* Everything it does is stored as an incident, visible at `/observability`.

See [permissions](permissions.md) and [ADR-004](adr/004-runbook-agent.md).
