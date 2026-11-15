# ADR-003: Built-in telemetry instead of an external stack

**Status:** accepted

**Context.** The key journey must emit metrics, traces and logs that share a trace ID and are viewable in a UI, with no customer data.

**Decision.** Implement W3C-compatible trace context, spans, structured logs and Prometheus metrics inside the app; store them in the database (24 h retention); view them at `/observability`; sanitise everything on the way in.

**Consequences.** One command gives the whole loop with no extra services; the alerter and agent read the same data. Trade-off: not for high volume. Migration path: export the same spans/logs through OpenTelemetry to Grafana Tempo/Loki/Prometheus; trace IDs already follow the W3C format.
