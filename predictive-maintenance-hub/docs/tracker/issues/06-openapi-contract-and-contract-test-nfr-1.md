# OpenAPI contract and contract test (NFR-1)

Labels: architecture, testing

**User story:** As a team we want the contract to be the source of truth.

**Owner agent:** architect
**Spec:** NFR-1

## Acceptance criteria
- [ ] Every route is in openapi.yaml and every documented route exists
- [ ] Real responses (including error statuses) validate against the schemas

## Verification
backend/tests/integration/test_openapi_contract.py
