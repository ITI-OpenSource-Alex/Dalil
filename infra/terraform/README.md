# GOA Terraform foundation

Terraform 1.7+ provisions the shared GOA networking and application foundation. The same root module is isolated into `staging` and `production` Terraform workspaces.

## One-time account bootstrap

Run from this directory with an authenticated AWS profile:

```bash
AWS_PROFILE=goa-production ./bootstrap.sh
terraform init -reconfigure -backend-config=environments/shared.backend.hcl
terraform workspace new staging
terraform workspace new production
```

The bootstrap creates one versioned, encrypted, private S3 state bucket and one DynamoDB lock table. Workspace state is stored below `environments/<workspace>/`.

## Validate and plan

```bash
terraform fmt -check -recursive
terraform validate
terraform workspace select staging
terraform plan -var-file=environments/staging.tfvars
terraform workspace select production
terraform plan -var-file=environments/production.tfvars
```

`create_self_signed_alb_certificate` is intended only for staging smoke tests. Production must receive an ACM certificate issued for its real domain. Image-based Lambda workers remain disabled until their images have been published. ECS repositories, task definitions, and services are managed here; desired counts default to zero so infrastructure can be bootstrapped before application images exist.

The current AWS free-plan staging account limits automated RDS backup retention
to one day. Production is configured for the GOA-070 requirement of seven
days. It also does not offer RDS Proxy, so staging connects directly over the
private ECS/RDS security-group path. Production keeps RDS Proxy enabled. Raise
staging retention to seven days and enable the proxy after the account plan is
upgraded.

Alert email addresses are intentionally not committed. Supply the team-owned
addresses through an uncommitted tfvars file or
`TF_VAR_alert_email_addresses='["team@example.com"]'`, apply Terraform, and
confirm the subscription from each SNS confirmation email.
