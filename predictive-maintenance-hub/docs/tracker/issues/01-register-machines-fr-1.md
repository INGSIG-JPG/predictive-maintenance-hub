# Register machines (FR-1)

Labels: backend, feature

**User story:** As a planner I register equipment so readings can be attached to it.

**Owner agent:** backend
**Spec:** FR-1; openapi: /api/machines

## Acceptance criteria
- [ ] Given a unique code, name and type, when I POST /api/machines then I get 201 and it appears in GET /api/machines
- [ ] Given a duplicate code then 409
- [ ] Given an invalid code, type or empty name then 422 with the failing field

## Verification
backend/tests/integration/test_journey_and_persistence.py
