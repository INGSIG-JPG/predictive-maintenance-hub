# ADR-002: Contract first (openapi.yaml)

**Status:** accepted

**Decision.** `openapi.yaml` is written and changed before code. `test_openapi_contract.py` checks that every route is documented, every documented route exists, and real responses (including error statuses) validate against the schemas.

**Consequences.** Frontend, backend and the on-call agent can work in parallel; drift fails CI.
