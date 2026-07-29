# GOA-073 production edge deployment

## Preconditions

- Confirm the organization owns `goa.app` and can change its registrar name
  servers. As of implementation, public DNS is delegated to Cloudflare, not
  the Route 53 zone this configuration will create.
- Complete the production container image publication required by GOA-071.
- Add the Next.js application to `apps/web` and produce a static export in
  `apps/web/out`. The directory currently contains only `.gitkeep`.
- Review the production plan and expected AWS cost. The production workspace
  is currently empty, so the plan creates the complete production foundation,
  not only the GOA-073 edge resources.

## Initialize and validate

```powershell
Set-Location "C:\Users\HP\Desktop\ITI\FINAL PROJECT\GOA\infra\terraform"
$env:AWS_PROFILE = "goa-production"
$env:AWS_DEFAULT_REGION = "eu-west-1"

terraform init -reconfigure -backend-config="environments/shared.backend.hcl"
terraform workspace select production
terraform fmt -check -recursive
terraform validate
terraform plan -var-file="environments/production.tfvars" -out="C:\tmp\goa073-production.tfplan"
```

## Bootstrap DNS, ECR, and the frontend bucket

The first targeted apply creates only resources needed before the full
production deployment. Targeting is intentionally limited to this one-time
bootstrap.

```powershell
terraform apply `
  -var-file="environments/production.tfvars" `
  -target="module.production_dns_zone" `
  -target="module.ecr" `
  -target="module.frontend_assets"

terraform output production_name_servers
```

Replace the Cloudflare name servers at the `goa.app` registrar with the four
Route 53 name servers printed by Terraform. Do not continue until public NS
lookups return those Route 53 servers:

```powershell
Resolve-DnsName goa.app -Type NS
```

## Publish application artifacts

Push all seven production images to the ECR URLs returned by:

```powershell
terraform output -json ecr_repository_urls
```

After the frontend task supplies a static Next.js export:

```powershell
aws s3 sync `
  "..\..\apps\web\out" `
  "s3://$(terraform output -raw frontend_assets_bucket_name)" `
  --delete
```

## Full production apply

Always regenerate the plan after the bootstrap apply:

```powershell
terraform plan `
  -var-file="environments/production.tfvars" `
  -out="C:\tmp\goa073-production-final.tfplan"

terraform apply "C:\tmp\goa073-production-final.tfplan"
```

Create an invalidation after subsequent frontend deployments:

```powershell
aws cloudfront create-invalidation `
  --distribution-id "$(terraform output -raw cloudfront_distribution_id)" `
  --paths "/*"
```

## Acceptance checks

```powershell
# API through the production ALB
curl.exe -i "https://api.goa.app/health"

# Populate and then verify the static cache
curl.exe -sS -D - -o NUL "https://goa.app/"
curl.exe -sS -D - -o NUL "https://goa.app/"

# SQL injection query must be blocked by WAF
curl.exe -sS -o NUL -w "%{http_code}`n" `
  "https://goa.app/?id=1%20OR%201%3D1--"

# Confirm both ACL associations
aws wafv2 get-web-acl-for-resource `
  --region eu-west-1 `
  --resource-arn "$(terraform output -raw alb_arn)"

aws cloudfront get-distribution `
  --id "$(terraform output -raw cloudfront_distribution_id)" `
  --query "Distribution.DistributionConfig.WebACLId"
```

The first two root responses must be `200`; the second response must include
`X-Cache: Hit from cloudfront`. The SQL-injection request must return `403`.

The rate-limit test deliberately generates production traffic. Run it only
from an approved test IP:

```powershell
1..1050 | ForEach-Object -Parallel {
  curl.exe -sS -o NUL "https://goa.app/health"
} -ThrottleLimit 50

curl.exe -sS -o NUL -w "%{http_code}`n" "https://goa.app/health"
```

WAF evaluates the rolling five-minute window asynchronously; retry the final
request for up to one minute. It must return `403`.
