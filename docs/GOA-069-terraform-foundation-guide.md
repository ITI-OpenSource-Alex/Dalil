# GOA-069 Terraform Core IaC Foundation Guide

## Goal

Build the initial Terraform foundation for GOA under `infra/terraform` so the project has a reusable AWS infrastructure layout for:

- VPC and subnets
- Internet and NAT routing
- Security groups
- Application Load Balancer
- VPC endpoints
- Baseline IAM roles and policies
- Environment-specific configuration
- Offline Terraform validation without real AWS credentials

## Important Constraints

- Work inside `infra/terraform`.
- Start with local state so `terraform init` and `terraform validate` can run without AWS credentials.
- Keep the future S3 backend block in `backend.tf`, but comment it out for now.
- Configure the AWS provider for offline validation using mock credentials and skip flags.
- Prepare two environments: `staging` and `production`.
- Default AWS region to `eu-west-1`, but keep it variable-driven.
- Default VPC CIDR to `10.0.0.0/16` in both environments unless you later confirm they must share one AWS account.

## Final Structure You Want

```text
infra/terraform/
  backend.tf
  providers.tf
  variables.tf
  main.tf
  outputs.tf
  bootstrap.sh
  environments/
    staging.tfvars
    production.tfvars
    staging.tfvars.example
    production.tfvars.example
  modules/
    vpc/
    nat-gateway/
    security-groups/
    alb/
    vpc-endpoints/
    iam/
    ecs-cluster/
    rds/
    elasticache/
    sqs/
    secrets/
    cloudfront/
    lambda/
    eventbridge/
    observability/
```

## Step-by-Step Plan

### Step 1: Create the Terraform skeleton

**Why**

This gives the project a predictable structure before you write any resources.

**What to create**

- Root files:
  - `infra/terraform/backend.tf`
  - `infra/terraform/providers.tf`
  - `infra/terraform/variables.tf`
  - `infra/terraform/main.tf`
  - `infra/terraform/outputs.tf`
  - `infra/terraform/bootstrap.sh`
- Environment folder:
  - `infra/terraform/environments/`
- Module folders:
  - `vpc`
  - `nat-gateway`
  - `security-groups`
  - `alb`
  - `vpc-endpoints`
  - `iam`
- Empty placeholder module folders:
  - `ecs-cluster`
  - `rds`
  - `elasticache`
  - `sqs`
  - `secrets`
  - `cloudfront`
  - `lambda`
  - `eventbridge`
  - `observability`

**Done when**

- The directory tree exists.
- Every non-empty module is ready to receive `main.tf`, `variables.tf`, and `outputs.tf`.

### Step 2: Build the VPC module

**Why**

This is the network foundation everything else depends on.

**What the module should manage**

- One VPC with CIDR `10.0.0.0/16`
- One Internet Gateway
- Two public subnets across two Availability Zones
- Four private subnets across two Availability Zones
  - Two private subnets for ECS/services
  - Two private subnets for RDS/ElastiCache
- Public route table
- Private route tables
- Route table associations

**Design expectations**

- Public subnets host ALB and NAT gateways.
- Private app subnets host ECS tasks/services.
- Private data subnets host stateful services.
- Spread everything across two AZs for high availability.

**Done when**

- The module outputs VPC ID, subnet IDs, IGW ID, and route table IDs.

### Step 3: Build the NAT Gateway module

**Why**

Private subnets need outbound internet access without becoming public.

**What the module should manage**

- Two Elastic IPs
- Two NAT Gateways
- Private route updates so private subnets use NAT for outbound traffic

**Design expectations**

- One NAT Gateway per public subnet
- One NAT Gateway per AZ for resilience

**Done when**

- ECS/private subnets can route outbound traffic through NAT.

### Step 4: Build the Security Groups module

**Why**

This defines the minimum safe traffic flow between layers.

**What the module should manage**

- ALB security group
  - Inbound `80` and `443` from the internet
- Gateway security group
  - Inbound only from ALB SG
- ECS services security group
  - Inbound only from Gateway SG
- RDS security group
  - Inbound only from ECS services SG
- ElastiCache security group
  - Inbound only from ECS services SG

**Design expectations**

- Use least privilege.
- Prefer SG-to-SG rules over wide CIDR rules for internal traffic.

**Done when**

- All layer-to-layer access is explicit and narrow.

### Step 5: Build the VPC Endpoints module

**Why**

This reduces NAT usage and keeps AWS service traffic private where possible.

**What the module should manage**

- Gateway endpoint for S3
- Interface endpoint for Secrets Manager
- Interface endpoint for SQS

**Design expectations**

- Interface endpoints should live in private subnets.
- Attach the correct security groups to interface endpoints.
- Associate S3 gateway endpoint with relevant route tables.

**Done when**

- Terraform defines private connectivity for these services without depending on public internet paths.

### Step 6: Build the ALB module

**Why**

This provides the public entry point for GOA services.

**What the module should manage**

- One Application Load Balancer in public subnets
- HTTP listener on port `80`
- HTTPS listener on port `443`
- HTTP to HTTPS redirect
- Target groups for internal services

**Design expectations**

- Keep certificate ARN variable-driven.
- Expose ALB DNS name and target group ARNs as outputs.

**Done when**

- The ALB module can front the gateway and future services cleanly.

### Step 7: Build the IAM module

**Why**

Tasks and operators need baseline permissions before workloads can run safely.

**What the module should manage**

- ECS task execution role
- ECS task role
- Least-privilege IAM policies
- ECS Exec / SSM access policy
- Policy attachments for task roles
- `aws_ssm_session_manager_preferences`

**Design expectations**

- Support ECS Exec securely through SSM channels
- Prepare for encrypted/logged Session Manager defaults

**Done when**

- Terraform exposes the required role ARNs and policies for future ECS modules.

### Step 8: Wire the root Terraform configuration

**Why**

The root module connects all reusable modules into one deployable stack.

**What to add**

- `backend.tf`
  - Active local backend
  - Commented S3 + DynamoDB backend block for later
- `providers.tf`
  - AWS provider
  - Mock credentials for local validation
  - Offline flags:
    - `skip_credentials_validation = true`
    - `skip_requesting_account_id = true`
    - `skip_metadata_api_check = true`
- `variables.tf`
  - `environment`
  - `aws_region`
  - `vpc_cidr`
  - AZs
  - subnet CIDRs
  - domain / hosted zone / certificate variables
  - tags / naming inputs
- `main.tf`
  - Instantiate `vpc`
  - Instantiate `nat-gateway`
  - Instantiate `security-groups`
  - Instantiate `vpc-endpoints`
  - Instantiate `alb`
  - Instantiate `iam`
- `outputs.tf`
  - VPC ID
  - subnet IDs
  - ALB DNS name
  - security group IDs
  - IAM role ARNs

**Done when**

- The root module composes all foundation modules without circular dependencies.

### Step 9: Add environment tfvars and examples

**Why**

This makes staging and production repeatable and easy to understand.

**What to create**

- `infra/terraform/environments/staging.tfvars`
- `infra/terraform/environments/production.tfvars`
- `infra/terraform/environments/staging.tfvars.example`
- `infra/terraform/environments/production.tfvars.example`

**What they should contain**

- `environment`
- `aws_region`
- `vpc_cidr`
- subnet CIDRs
- AZ names
- domain and certificate placeholders
- HA-related values for production
- comments warning about CIDR overlap if both environments share the same AWS account

**Done when**

- You can switch environments using the correct var file with minimal edits.

### Step 10: Add the bootstrap script

**Why**

When AWS credentials are available later, you will need remote state infrastructure only once per account/environment.

**What `bootstrap.sh` should do**

- Accept an environment argument
- Create the S3 bucket for Terraform state
- Create the DynamoDB table for state locking
- Use AWS CLI commands
- Be safe to run once per account with clear naming conventions

**Done when**

- The script documents how remote backend infrastructure will be created later.

### Step 11: Run offline verification

**Why**

You need proof that the Terraform configuration is structurally correct before real AWS access exists.

**Commands to run**

```bash
cd infra/terraform
terraform init -backend=false
terraform validate
```

**What success means**

- Terraform downloads providers successfully
- No syntax errors
- No broken variable references
- No broken module references

## Suggested Build Order Inside Each Real Module

For each non-placeholder module, keep the same internal layout:

- `main.tf` for resources
- `variables.tf` for inputs
- `outputs.tf` for exported values

This keeps every module consistent and easier to debug.

## Key Decisions to Document While You Build

Keep notes in comments or docs for these choices:

- Why `eu-west-1` is the default region
- Why local backend is active first
- When to switch to remote state
- Why both environments currently use `10.0.0.0/16`
- What must change if staging and production share one AWS account
- Which future modules are intentionally placeholders only

### Recorded Foundation Decisions

- `eu-west-1` is the default region because it keeps the foundation region-specific and predictable while still allowing each environment to override `aws_region`.
- Local backend is active first so `terraform init -backend=false` and `terraform validate` can run before real AWS credentials or remote-state infrastructure exist.
- Remote state should be enabled after `bootstrap.sh <environment>` creates the S3 state bucket and DynamoDB lock table with real AWS credentials.
- Staging and production currently both use `10.0.0.0/16` so each environment starts from the same easy-to-read network shape during foundation work.
- If staging and production share one AWS account and region, one environment must move to a non-overlapping CIDR before apply, for example `10.1.0.0/16`.
- `ecs-cluster`, `rds`, `elasticache`, `sqs`, `secrets`, `cloudfront`, `lambda`, `eventbridge`, and `observability` are intentionally placeholder modules until their dedicated infrastructure steps are implemented.

## Definition of Done

The task is complete when:

1. `infra/terraform` has the full root/module structure.
2. The VPC, NAT, SG, ALB, VPC endpoints, and IAM modules exist and are wired from the root module.
3. `staging` and `production` tfvars files exist.
4. `bootstrap.sh` exists for future backend provisioning.
5. `terraform init -backend=false` succeeds.
6. `terraform validate` succeeds.

## Recommended Execution Order for You

If you want the simplest implementation flow, do the work in this exact order:

1. Create folders and empty Terraform files.
2. Implement `modules/vpc`.
3. Implement `modules/nat-gateway`.
4. Implement `modules/security-groups`.
5. Implement `modules/vpc-endpoints`.
6. Implement `modules/alb`.
7. Implement `modules/iam`.
8. Wire the root files.
9. Add `tfvars` and examples.
10. Add `bootstrap.sh`.
11. Run offline validation.

## File Location

This guide lives at:

- `docs/GOA-069-terraform-foundation-guide.md`
