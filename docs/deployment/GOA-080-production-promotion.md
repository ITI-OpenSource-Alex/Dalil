# GOA-080 Production Promotion

## GitHub environment gate

Create or update the GitHub Actions environment named `production`:

1. Open Settings > Environments > `production`.
2. Enable Required reviewers.
3. Add at least one named reviewer from the release owner list.
4. Keep "Prevent self-review" enabled when available.

The deploy workflow uses `environment: production`, so GitHub pauses the job
until a listed reviewer clicks Approve in the Actions UI.

## Required repository variables

- `STAGING_INFRA_READY=true`
- `AWS_ROLE_TO_ASSUME` or `STAGING_AWS_ROLE_TO_ASSUME`
- `PRODUCTION_AWS_ROLE_TO_ASSUME`
- `STAGING_BASE_URL`
- `PRODUCTION_BASE_URL`
- `AWS_REGION=eu-west-1`
- Optional: `SLACK_WEBHOOK_URL` secret for production deploy notifications

## Flow

1. Merge to `dev`.
2. Staging deploy workflows run for changed services.
3. `Promote Staging to Production` runs staging Playwright E2E against
   `STAGING_BASE_URL`.
4. If E2E passes, it creates or updates a `dev` to `main` PR with:
   staging image tags/digests, last-hour ECS metrics, commits, and diff stat.
5. Reviewer approves and merges the PR.
6. `Deploy Production` starts on `main` and pauses at the `production`
   environment gate.
7. Reviewer approves the environment gate.
8. The deploy copies the exact staged image manifests into production ECR,
   updates production ECS services, runs smoke tests, and rolls ECS services
   back to their previous task definitions if smoke fails within five minutes.

## Verification To Record In The PR

- Gate test: production job paused until a production reviewer approved it.
- SHA test: production ECS task definition image tags and ECR digests matched
  the staging images listed in the promotion summary.
- Rollback test: a forced production smoke failure restored the previous ECS
  task definitions.
- Cross-service test: the user-facing flow was exercised through the Gateway
  from the real client entry point against staging.
