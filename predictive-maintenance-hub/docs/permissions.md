# Permissions and secrets

| Actor | Credential | Can do |
|---|---|---|
| Anyone on the internal network | none | Read/write machines, readings, work orders; view observability |
| Alerter | `ADMIN_TOKEN` | Create/resolve alerts; read telemetry |
| On-call agent | `ADMIN_TOKEN`, `WEBHOOK_SECRET` | Read config/traces; `config_rollback`, `verify`; record incidents; resolve alerts; send canary readings |
| Operator | `ADMIN_TOKEN` | Change config (validated), roll back, verify |

* `APP_ENV=production` **refuses to start** with the default admin token.
* `ENABLE_FAULT_INJECTION` (accepts `skip_validation` on config changes, used only for incident drills) defaults to **off in production**
  and returns `403` when disabled.
* Secrets come from environment variables / repository secrets, never from git. `.env.example` has placeholders only.
* The agent's write allow-list is enforced in code (`ALLOWED_ACTIONS`) and tested.
