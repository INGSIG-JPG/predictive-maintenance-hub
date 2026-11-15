# Containerise the whole system (NFR-5)

Labels: devops

**User story:** As a developer I start everything with one command.

**Owner agent:** devops
**Spec:** NFR-5

## Acceptance criteria
- [ ] docker compose up --build starts db, app, alerter, responder
- [ ] App waits for a healthy database
- [ ] Smoke test passes against the compose stack

## Verification
Dockerfile, docker-compose.yml, ci.yml containers job
