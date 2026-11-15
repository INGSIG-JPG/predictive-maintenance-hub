# Workflow

```
spec  ->  issue (acceptance criteria)  ->  branch  ->  contract change  ->  tests + code  ->  PR  ->  CI  ->  merge  ->  deploy dev  ->  manual deploy prod
```

1. **Specify.** Requirements live in [product-spec.md](../../product-spec.md). A change in behaviour starts as a spec change.
2. **Issue.** Open an issue from the *Feature* template: Given/When/Then acceptance criteria, owner agent, spec link.
3. **Branch.** `feature/<issue-number>-<slug>`.
4. **Contract first.** Update [openapi.yaml](../../openapi.yaml) if a route or response changes.
5. **Tests first or together.** Unit tests for pure logic, integration tests for behaviour across API and database.
6. **Open a PR** with `Closes #<n>`, the verification evidence (`make test` output) and notes for the reviewer agent.
7. **CI must be green** (`ci.yml`): unit, integration (SQLite and PostgreSQL), frontend, compose smoke test.
8. **Merge to `main`** &rarr; `deploy-dev.yml` deploys to dev and smoke-tests it.
9. **Release to production** manually with `deploy-prod.yml`; the `production` environment requires approval.
10. **Rollback** = run `deploy-prod.yml` with the previous known-good ref ([deployment](../deployment.md)).

## Branch and commit conventions

Small commits, imperative subject, reference the issue: `Add work-order transitions (#7)`.
Agents add a trailer naming the agent role in PR descriptions (for example `Agent: backend`).
