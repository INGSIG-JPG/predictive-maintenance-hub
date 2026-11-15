# Full-stack tests with a single command (NFR-5)

Labels: testing

**User story:** As a reviewer I run all tests with one command.

**Owner agent:** qa
**Spec:** NFR-5

## Acceptance criteria
- [ ] make test runs unit, integration, on-call and frontend tests
- [ ] Unit and integration are separated by pytest markers
- [ ] Integration suite also runs on PostgreSQL in CI

## Verification
Makefile, pytest.ini, ci.yml
