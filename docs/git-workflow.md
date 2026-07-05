# Git Workflow

This document defines the branching strategy, pull request (PR) process, review gates, and deployment flows for the GOA codebase.

---

## Branching Strategy

We use a modified Git Flow strategy:

* **`main`**: Represents the current production-ready code. Direct push is blocked.
* **`develop`**: Represents the current staging/integration state of active development. All feature branches are merged here. Direct push is blocked.
* **`feat/GOA-XXX-Name`**: Feature branches created off `develop` to implement a specific ticket.
* **`fix/GOA-XXX-Name`**: Bugfix branches created off `develop` to resolve issues.

---

## Pull Request & Merge Guidelines

To merge code into `develop` or `main`:

1. **Self-Review**: Ensure all changes are linted, formatted, and all tests pass locally.
2. **Open PR**: Target the `develop` branch from your feature/fix branch.
3. **Automated CI Checks**: GitHub Actions CI workflow triggers automatically:
   * **Go**: Runs `golangci-lint` and `go test ./...`.
   * **TypeScript/Node**: Runs `eslint` and `jest --coverage` (requires ≥70% coverage).
   * **Python**: Runs `ruff` and `pytest --cov` (requires ≥70% coverage).
4. **Peer Review**: At least **1 approval** from a team member is required before merging.
5. **Merge**: Once PR is approved and all CI checks pass, squash and merge into `develop`.

---

## Deployment Gates

### Staging Deployment
* Triggered automatically upon a push or merge to the `develop` branch.
* GitHub Actions leverages OpenID Connect (OIDC) to assume the staging AWS deployment IAM role (no static keys in repo) and deploys to the ECS staging cluster.

### Production Deployment
* Triggered upon merging `develop` into `main`.
* A **named reviewer approval gate** must be clicked and approved in the GitHub Actions environment before deployment to production begins.
