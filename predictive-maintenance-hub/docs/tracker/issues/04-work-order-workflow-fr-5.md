# Work-order workflow (FR-5)

Labels: backend, feature

**User story:** As a technician I progress and close work orders.

**Owner agent:** backend
**Spec:** FR-5; openapi: /api/work-orders

## Acceptance criteria
- [ ] open -> in_progress -> done; done is final (409)
- [ ] Unknown status or fields give 422; unknown id gives 404
- [ ] Assignee can be set

## Verification
test_work_order_lifecycle_and_invalid_transitions
