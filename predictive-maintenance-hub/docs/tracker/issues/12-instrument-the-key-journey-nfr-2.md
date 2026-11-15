# Instrument the key journey (NFR-2)

Labels: observability

**User story:** As an engineer I can follow one reading through the system.

**Owner agent:** observability
**Spec:** NFR-2

## Acceptance criteria
- [ ] Metrics, spans and structured logs share one trace ID
- [ ] Responses carry X-Trace-Id and W3C traceparent; incoming traceparent is continued
- [ ] Signals are stored and viewable at /observability and /metrics
- [ ] No credentials or customer data are stored in telemetry

## Verification
test_observability.py, test_telemetry.py
