# Runbook: journey failing after a config change

**Alert:** `ingest_reading_error_rate`. **Automated:** yes (on-call agent). **Manual steps if the agent escalated:**

1. Open `/observability`, filter error traces, open one: the failing span and error message show the cause.
2. `GET /admin/config` (bearer token): look at `history` for the latest change and who made it.
3. `POST /admin/config/risk_model/rollback` restores the last verified-good value.
4. Send a reading (or run `python scripts/smoke_test.py <url>`); expect `201`.
5. `PATCH /api/alerts/{id}` `{"status":"resolved"}` and file an *Incident follow-up* issue.

**Prevention:** config changes are validated; `skip_validation` exists only for drills and is disabled in production.
