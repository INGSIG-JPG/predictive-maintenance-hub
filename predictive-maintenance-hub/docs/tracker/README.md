# Tracker and traceability

The backlog below is loaded into GitHub Issues with `python scripts/create_issues.py` (needs the GitHub CLI, `gh auth login`). Process: [docs/process/tracker.md](../process/tracker.md).

| # | Issue | Requirement | Verified by |
|---|---|---|---|
| 1 | Register machines (FR-1) | FR-1 | backend/tests/integration/test_journey_and_persistence.py |
| 2 | Record and score a sensor reading (FR-2, FR-3) | FR-2, FR-3 | backend/tests/unit/test_risk.py, test_validation.py, integration tests |
| 3 | Automatic work orders without duplicates (FR-4) | FR-4 | test_critical_reading_opens_one_p1_work_order_and_dedupes, test_auto_work_orders_can_be_disabled |
| 4 | Work-order workflow (FR-5) | FR-5 | test_work_order_lifecycle_and_invalid_transitions |
| 5 | Dashboard and persistence (FR-6, FR-7) | FR-6, FR-7 | test_data_persists_across_app_instances, frontend/tests |
| 6 | OpenAPI contract and contract test (NFR-1) | NFR-1 | backend/tests/integration/test_openapi_contract.py |
| 7 | Runtime config with history and rollback (FR-8) | FR-8, NFR-7 | test_admin_and_incident_primitives.py |
| 8 | Full-stack tests with a single command (NFR-5) | NFR-5 | Makefile, pytest.ini, ci.yml |
| 9 | Containerise the whole system (NFR-5) | NFR-5 | Dockerfile, docker-compose.yml, ci.yml containers job |
| 10 | CI on every PR; CD to dev; manual prod deploy (NFR-6) | NFR-6 | .github/workflows |
| 11 | Deploy to a public URL | NFR-6 | docs/deployment.md |
| 12 | Instrument the key journey (NFR-2) | NFR-2 | test_observability.py, test_telemetry.py |
| 13 | Alert on user impact (NFR-3) | NFR-3 | ops/alerts/alert-rules.yaml, oncall/tests |
| 14 | On-call agent fixes a bad config push (NFR-4) | NFR-4 | oncall/tests/test_oncall_e2e.py, scripts/simulate_incident.py |
| 15 | Security hardening (NFR-7) | NFR-7 | test_db.py, test_admin_and_incident_primitives.py |
