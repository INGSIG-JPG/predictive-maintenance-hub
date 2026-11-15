# ADR-001: Flask with portable SQL on SQLite and PostgreSQL

**Status:** accepted

**Context.** We need a small, reviewable full-stack app that runs with one command and also in production.

**Decision.** Flask + gunicorn; a thin DB layer using `?` placeholders and `INSERT ... RETURNING id` that works on SQLite (3.35+) and PostgreSQL. SQLite for local dev and fast tests, PostgreSQL for compose and deployment; CI runs the integration suite on both.

**Consequences.** No ORM migrations: schema is created idempotently at start. Fine for this scope; adopt Alembic if the schema starts evolving in production.
