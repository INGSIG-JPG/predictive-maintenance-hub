# Task tracker

The tracker is the repository's **public GitHub Issues** plus a GitHub Project board (columns: Backlog, In progress, Review, Done).

* The initial backlog is in [docs/tracker/issues](../tracker/issues) (one file per issue, with acceptance criteria) and can be
  loaded with `python scripts/create_issues.py` (uses the GitHub CLI). Traceability: [docs/tracker/README.md](../tracker/README.md).
* Every issue has: user story, **Given/When/Then acceptance criteria**, owner agent, link to the spec section and `openapi.yaml` paths.
* Agents update the tracker as part of their work: they comment progress, link PRs (`Closes #n`) and tick criteria in the issue body.
* **Evidence of use** is the issue/PR history: each closed issue links the PR whose CI run shows the acceptance tests passing.
* Bugs found by the on-call agent or in production are filed with the *Incident follow-up* template, linking the incident record.
