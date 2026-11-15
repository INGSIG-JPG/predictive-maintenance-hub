# Definition of done

A change is done when **all** of these hold:

- [ ] Acceptance criteria of the issue are met and each one is covered by a test.
- [ ] `make test` passes locally and CI is green (including PostgreSQL).
- [ ] `openapi.yaml` matches the code (contract test green).
- [ ] No secrets, tokens, e-mails or assignee names reach logs, spans or metrics (sanitisation tests green).
- [ ] New behaviour in the key journey is visible in `/observability` (span or log with the trace ID).
- [ ] Docs updated (README, spec or runbook) when behaviour or operations changed.
- [ ] The PR states how it was verified; unverified parts are listed.

## Testing rules

| Kind | Scope | Location | Marker |
|---|---|---|---|
| Unit | Pure functions, no HTTP, no DB server | `backend/tests/unit`, `oncall/tests/test_rules_unit.py`, `frontend/tests` | `unit` |
| Integration | API + real database, contract, observability, alert &rarr; agent | `backend/tests/integration`, `oncall/tests/test_oncall_e2e.py` | `integration` |

Run everything with `make test`. Integration tests run on SQLite by default and on PostgreSQL with `TEST_DATABASE_URL`.
