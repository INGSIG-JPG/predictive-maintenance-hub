# Dashboard and persistence (FR-6, FR-7)

Labels: frontend, feature

**User story:** As a planner I see fleet risk at a glance and my data survives restarts.

**Owner agent:** frontend
**Spec:** FR-6, FR-7

## Acceptance criteria
- [ ] Dashboard shows totals, per-level counts, open work orders, readings in 24 h and active model
- [ ] Machines table shows latest risk; forms register machines and record readings with instant validation
- [ ] Data persists across app instances (database, not memory)

## Verification
test_data_persists_across_app_instances, frontend/tests
