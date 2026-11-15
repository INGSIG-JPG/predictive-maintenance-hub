# ADR-004: Runbook-driven on-call agent

**Status:** accepted

**Context.** Production changes made autonomously must be predictable and auditable.

**Decision.** The on-call agent is a deterministic runbook executor with a single write permission (`config_rollback`), dry-run mode, mandatory verification by canary requests, and escalation for anything it cannot attribute. An LLM can be added later for diagnosis only, behind the same allow-list.

**Consequences.** Safe and testable end to end; limited to the failure classes it knows.
