# Runtime config with history and rollback (FR-8)

Labels: backend, feature

**User story:** As an operator I change config safely and can undo it.

**Owner agent:** backend
**Spec:** FR-8, NFR-7

## Acceptance criteria
- [ ] Invalid values are rejected (422) unless fault injection is enabled
- [ ] Every change is recorded with actor and verified flag
- [ ] Rollback restores the latest verified-good value; 409 when none exists
- [ ] Admin endpoints require a bearer token

## Verification
test_admin_and_incident_primitives.py
