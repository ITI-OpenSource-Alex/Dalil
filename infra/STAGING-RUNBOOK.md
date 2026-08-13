# Staging: build, load test, tear down

Everything needed to stand up staging, run GOA-036 against it, and destroy it
again. Written 2026-08-11 as part of GOA-030/036.

The four blockers that previously made a deployed environment unable to serve a
request are fixed in code and Terraform (see §1). What remains is execution.

---

## 0. Prerequisites

- AWS credentials for account `114403655381` with permission to create VPC, ECS,
  RDS, ElastiCache, ALB, SQS, Secrets Manager and IAM resources.
  (`ce:GetCostAndUsage` is denied by the `DenyBillingAccess` policy, so cost has
  to be read from the console, not the CLI.)
- Docker with ~15 GB free — the images total roughly 12 GB.
- `terraform` 1.7+, `psql`, `k6` (or Docker, which the runner uses).

---

## 1. What was broken, and what fixed it

| Blocker | Why it stopped staging working | Fix |
|---|---|---|
| **ECR empty** | Zero repositories; `ecs_image_tag` defaulted to the placeholder `bootstrap`, so every ECS task would fail to pull and crash-loop | `infra/build-and-push.sh` builds and pushes all 10 images; `ecs_image_tag` pinned to a real, bumpable tag in `staging.tfvars` |
| **RAG had no embeddings endpoint** | Fell back to `host.docker.internal:11434` — the developer's own Ollama — so every `/query` and `/match` failed at the embedding call, quietly | New `embeddings` ECS service running Ollama with `nomic-embed-text` baked in; `EMBEDDING_BASE_URL` wired through Service Connect |
| **Speaking had no STT** | Defaulted to `http://speech:8086`, which resolved to nothing in the VPC, so every transcription failed and the swarm graded an empty transcript | `speech` added as an ECS service; `SPEECH_SERVICE_URL` wired through Service Connect |
| **RDS would be empty** | The load test's meaning comes from the catalogue; a fresh RDS has none | §4 restores a 16 MB data-only dump of the six catalogue tables |

**Why Ollama rather than a hosted embedding API.** The 3,979 chunks in the
catalogue were embedded with `nomic-embed-text` at 768 dimensions. Embeddings
from different models do not share a vector space, so pointing staging at, say,
OpenAI's `text-embedding-3-small` would not degrade quality — it would make
every similarity score meaningless while still returning plausible numbers and
erroring nowhere. Changing the model is a re-embed of the whole corpus, not a
config change.

---

## 2. Build and push images

```bash
cd "$(git rev-parse --show-toplevel)"
bash infra/build-and-push.sh build     # local only, no AWS, ~30-60 min cold
```

Contexts differ per service and are not guesswork: `orchestration`, `writing`,
`rag` and `ingestion` COPY from `packages/`, so they build only from the repo
root; the rest build from their own directory. Getting it wrong produces
`failed to calculate checksum ... not found`.

`--platform linux/amd64` is set for every build. Fargate is amd64, and a
silently-built arm64 image fails at task start with an exec format error that
reads like a broken entrypoint.

Push happens after §3, because the repositories do not exist until Terraform
creates them:

```bash
bash infra/build-and-push.sh push
```

ECR repositories are **immutable**: a tag is written once. To redeploy, bump
`IMAGE_TAG` and `ecs_image_tag` together and re-apply.

---

## 3. Apply the infrastructure

```bash
cd infra/terraform
terraform init -reconfigure -backend-config=environments/shared.backend.hcl
terraform workspace new staging      # first time only
terraform workspace select staging
terraform plan -var-file=environments/staging.tfvars -out=staging.tfplan
terraform apply staging.tfplan
```

**518 resources.** Expect 20–30 minutes; RDS is the long pole.

Then push the images (§2) and force the services to pull them:

```bash
CLUSTER=goa-staging
for s in gateway user orchestration speaking writing rag exam speech embeddings; do
  aws ecs update-service --cluster "$CLUSTER" --service "goa-staging-$s" \
    --force-new-deployment --region eu-west-1 >/dev/null
done
```

Wait for steady state:

```bash
aws ecs describe-services --cluster goa-staging --region eu-west-1 \
  --services $(aws ecs list-services --cluster goa-staging --region eu-west-1 \
    --query 'serviceArns' --output text) \
  --query 'services[].[serviceName,runningCount,desiredCount]' --output table
```

---

## 4. Migrate and seed

Migrations run as one-off ECS tasks (`ecs_migration_tasks.tf`):

```bash
for s in user orchestration speaking writing rag exam; do
  aws ecs run-task --cluster goa-staging --region eu-west-1 \
    --task-definition "goa-staging-$s-migration" \
    --launch-type FARGATE --network-configuration "$NETWORK_CONFIG"
done
```

Seed the catalogue. The dump is data-only for the six tables that carry it, so
migrations must have created the schema (including the pgvector extension)
first:

```bash
docker compose exec -T postgres pg_dump -U goa -d rag_db \
  --data-only --no-owner --no-privileges \
  -t program_requirements -t documents -t visa_requirements \
  -t visa_sources -t faq_entries -t scholarship_programs \
  | gzip > rag_seed.sql.gz          # ~16 MB
```

RDS sits in a private data subnet with no public access, so load it from
**inside** the VPC rather than by opening it up. Upload the dump to the
ingestion reports bucket and run a one-off task on the `postgres:15` public
image with the RAG task role:

```bash
aws s3 cp rag_seed.sql.gz "s3://$(terraform output -raw ingestion_reports_bucket)/seed/rag_seed.sql.gz"
```

Verify afterwards — the counts are what make the load test meaningful:

```
program_requirements  3805   (3793 non-seed)
documents             3979
visa_requirements       19
```

---

## 5. Load test

The harness needs no code change; it takes the Gateway from the environment.

```bash
export GATEWAY_HOST="https://$(terraform output -raw alb_dns_name)"
LOAD_SCALE=0.1 LOAD_DURATION=10m ./perf/run-load-test.sh
```

Two things to know:

- The ALB certificate is **self-signed** (`create_self_signed_alb_certificate =
  true` in staging), so k6 needs `--insecure-skip-tls-verify` and
  `provision_load_users.py` needs `verify=False`. Both are local-only
  concessions to a staging cert and must not be carried into a run against a
  real certificate.
- The per-feature rate limits are what bounded the local run — 77% of requests
  were 429s. If the point is to measure the *system*, raise them for the run:
  `CHAT_QUERIES_PER_HOUR`, `OPPORTUNITY_SEARCHES_PER_HOUR`, `ESSAY_EVALS_PER_HOUR`.

---

## 6. Destroy — do not skip

```bash
cd infra/terraform
terraform workspace select staging
terraform destroy -var-file=environments/staging.tfvars
```

Then verify nothing survives, because a failed destroy is silent and bills daily:

```bash
R=eu-west-1
aws ecs list-clusters --region $R --query 'clusterArns' --output text
aws rds describe-db-instances --region $R --query 'DBInstances[].DBInstanceIdentifier' --output text
aws elbv2 describe-load-balancers --region $R --query 'LoadBalancers[].LoadBalancerName' --output text
aws elasticache describe-cache-clusters --region $R --query 'CacheClusters[].CacheClusterId' --output text
aws ec2 describe-nat-gateways --region $R --query 'NatGateways[?State==`available`].NatGatewayId' --output text
```

All five must come back empty. The NAT gateway and RDS are the two that cost
real money if they linger.

ECR repositories and their images survive `destroy` only if
`force_delete` is set; check them too, since stored images bill per GB-month.

---

## 7. What this costs while it is up

Not measurable from this account (`ce:GetCostAndUsage` is denied), so read it
from the billing console. The standing hourly items are the NAT gateway,
`db.t3.micro` RDS, `cache.t3.micro` ElastiCache, the ALB, and 9 Fargate tasks —
the NAT gateway and ALB dominate at low utilisation, and neither scales down.

Tear down the same day. The environment has no reason to exist between runs.
