# Runbook: slow readings (`ingest_reading_latency_p95`)

**Automated:** no, escalated to a human (no safe automated fix).

1. `/observability`: sort traces by duration; which child span dominates (`risk.score` vs `db.insert_reading`)?
2. `risk.score` slow with model `v2`: history lookup grows with readings per machine; check indexes and consider `risk_model=v1` (validated change).
3. `db.insert_reading` slow: check database load and connections; scale the database plan.
4. After the fix, confirm the p95 tile at `/observability` returns below 1.5 s; resolve the alert.
