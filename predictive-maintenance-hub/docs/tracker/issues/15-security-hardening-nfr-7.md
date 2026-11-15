# Security hardening (NFR-7)

Labels: security

**User story:** As an owner I do not ship insecure defaults.

**Owner agent:** devops
**Spec:** NFR-7

## Acceptance criteria
- [ ] Production refuses to start with the default admin token
- [ ] Fault injection is off by default in production (403)
- [ ] UI uses textContent only; SQL is parameterised

## Verification
test_db.py, test_admin_and_incident_primitives.py
