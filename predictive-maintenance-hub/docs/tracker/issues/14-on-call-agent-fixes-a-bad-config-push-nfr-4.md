# On-call agent fixes a bad config push (NFR-4)

Labels: oncall

**User story:** As on-call I want the system to recover without waking me.

**Owner agent:** oncall
**Spec:** NFR-4

## Acceptance criteria
- [ ] On alert the agent diagnoses from traces and config history
- [ ] It rolls back to the last verified-good config, verifies with 3 canary readings, resolves the alert and records an incident
- [ ] Unknown causes and latency alerts are escalated without any write
- [ ] Only config_rollback is permitted; dry-run mode exists

## Verification
oncall/tests/test_oncall_e2e.py, scripts/simulate_incident.py
