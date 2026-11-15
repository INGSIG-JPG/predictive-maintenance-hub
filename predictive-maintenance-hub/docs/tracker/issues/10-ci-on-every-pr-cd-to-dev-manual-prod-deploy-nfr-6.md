# CI on every PR; CD to dev; manual prod deploy (NFR-6)

Labels: devops

**User story:** As a team we ship safely.

**Owner agent:** devops
**Spec:** NFR-6

## Acceptance criteria
- [ ] CI runs on every pull request
- [ ] Merge to main deploys to dev automatically after CI and smoke-tests it
- [ ] Production deploy is manual, needs approval and can deploy an older ref (rollback)

## Verification
.github/workflows
