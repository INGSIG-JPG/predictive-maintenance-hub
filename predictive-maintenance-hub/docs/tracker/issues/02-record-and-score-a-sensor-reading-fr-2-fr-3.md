# Record and score a sensor reading (FR-2, FR-3)

Labels: backend, feature

**User story:** As an operator I record readings and see a risk level immediately.

**Owner agent:** backend
**Spec:** FR-2, FR-3; openapi: /api/readings

## Acceptance criteria
- [ ] Given a registered machine, when I POST a valid reading then 201 with risk score 0-100, level and X-Trace-Id header
- [ ] Unknown machine gives 404; invalid or out-of-range values give 422
- [ ] v1 boundaries 40/70/85 are covered; v2 adds an outlier bonus and never exceeds 100

## Verification
backend/tests/unit/test_risk.py, test_validation.py, integration tests
