# GOA-036 — staging teardown verification

**2026-08-11.** Run immediately after the staging load test
(`GOA-036-staging-report.md`).

`terraform destroy -var-file=environments/staging.tfvars` completed with
**486 resources destroyed, 0 errors**.

## Verified empty

Every class checked directly against the AWS API, not inferred from the destroy
log — a failed destroy is silent and bills daily.

| Resource | Query | Result |
|---|---|---|
| NAT gateways | `describe-nat-gateways` (State=available) | **empty** |
| RDS instances | `describe-db-instances` | **empty** |
| Load balancers | `describe-load-balancers` | **empty** |
| ElastiCache clusters | `describe-cache-clusters` | **empty** |
| ECS clusters | `list-clusters` | **empty** |
| EC2 instances | `describe-instances` (running) | **empty** |
| Elastic IPs | `describe-addresses` | **empty** |
| VPCs | `describe-vpcs` (tag:Project=goa) | **empty** |
| Secrets Manager | `list-secrets` (goa-staging) | **empty** |
| S3 buckets | `list-buckets` (staging) | **empty** |
| CloudWatch log groups | `describe-log-groups` (staging) | **empty** |
| ECR repositories | `describe-repositories` | **empty** |

The two that needed manual attention, because `terraform destroy` does not
remove them:

- **10 ECR repositories** survived the destroy — they hold images and
  `force_delete` is not set, which is the safe default but means ~17.7 GB
  billing per GB-month indefinitely. Deleted with `--force`.
- **1 CloudWatch log group**, `/aws/ecs/containerinsights/goa-staging/performance`,
  created by Container Insights rather than by Terraform. Deleted.

## Deliberately left in place

| Item | Why |
|---|---|
| `goa-staging-deploy` (IAM role) | Pre-existing and **not managed by Terraform** — it is not in the config and was not in the apply's failure list. Nearly deleted during the orphaned-IAM cleanup; excluded on purpose. IAM roles cost nothing. |
| `goa-114403655381-eu-west-1-terraform-state` (S3) | The Terraform state backend. Pre-existed this work; deleting it would strand every workspace. Cents per month. |
| `goa-eu-west-1-terraform-locks` (DynamoDB) | State locking, same reasoning. |
| GitHub OIDC provider, `SSM-SessionManagerRunShell` | Account-global and shared with CI. Deliberately never imported into the staging workspace, precisely so a staging teardown could not delete the account's CI trust. |

## Standing cost after teardown

**Effectively zero.** The state bucket and lock table are the only remaining
resources, at cents per month. No compute, no storage of consequence, no NAT
gateway, no load balancer.

## For next time

`terraform destroy` alone is **not** sufficient to stop the meter. Two things
outlive it:

```bash
# ECR repositories still holding images
aws ecr describe-repositories --region eu-west-1 --query 'repositories[].repositoryName' --output text

# Container Insights log groups Terraform never created
aws logs describe-log-groups --region eu-west-1 --query 'logGroups[].logGroupName' --output text | tr '\t' '\n' | grep staging
```

Both are in the teardown section of `infra/STAGING-RUNBOOK.md`.
