# Alert on user impact (NFR-3)

Labels: observability

**User story:** As on-call I am paged on user impact, not CPU.

**Owner agent:** observability
**Spec:** NFR-3

## Acceptance criteria
- [ ] Alert rules use the journey error ratio and p95 latency
- [ ] Low traffic does not page; a firing alert is not duplicated

## Verification
ops/alerts/alert-rules.yaml, oncall/tests
