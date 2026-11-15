# Automatic work orders without duplicates (FR-4)

Labels: backend, feature

**User story:** As a planner I want a work order when a machine degrades.

**Owner agent:** backend
**Spec:** FR-4

## Acceptance criteria
- [ ] high -> P2, critical -> P1 work order, status open
- [ ] A machine with a non-done work order does not get a duplicate
- [ ] auto_work_orders=false disables creation

## Verification
test_critical_reading_opens_one_p1_work_order_and_dedupes, test_auto_work_orders_can_be_disabled
