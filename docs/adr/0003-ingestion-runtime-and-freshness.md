# ADR 0003: Production ingestion runtime and freshness signals

- **Status:** Accepted
- **Date:** 2026-07-30
- **Ticket:** GOA-041

## Decision

`services/ingestion/handler.py` is the only ingestion entry point. The discarded
orchestrator and its separate S3 reporter are deleted.

Production ingestion runs as a bounded ECS Fargate worker, not Lambda. EventBridge
publishes the weekly MastersPortal Tier 1 job and monthly visa-verification job to
the ingestion queue with explicit adapter, tier, item, and time budgets. Queue depth
scales the ingestion ECS service from zero. This indirection is required because a
standalone EventBridge Fargate task does not inherit the ECS service's Service
Connect client and therefore cannot resolve RAG. The queue consumer leaves failed
messages undeleted, allowing the queue's three-attempt redrive policy and DLQ to
handle application failures.

The browser-facing admin shape is
`POST /api/admin/ingestion/run`, authenticated by GOA-027's `X-Admin-Key`. It
validates the selected adapters, tier, dry-run flag, and optional work budgets,
then returns `202` plus a job id after publishing to the same ingestion queue.
Dry runs are asynchronous and are identified by that job id; they do not write
crawl state, RAG data, or an S3 report, and they do not call an LLM.

Short-lived batch metrics use structured JSON logs in CloudWatch Embedded Metric
Format under `GOA/Ingestion`. Prometheus is intentionally not used because this
worker has no continuously available scrape endpoint. S3 completion reports remain
the durable per-run evidence.

## BUG-013 disposition

BUG-013 (Egypt/APS coverage) is deferred to its own corpus-language ticket.
`aps-egypt.de` did not resolve during the ticket investigation, and
`kairo.diplo.de` had no English edition. The current corpus and prompts are English,
while embeddings use `nomic-embed-text`. Adding German or Arabic content therefore
requires an explicit choice among translation at ingestion, a multilingual
embedding migration, or knowingly poorer retrieval. That product/retrieval decision
is outside GOA-041's deployment and freshness scope.

## Verification boundary

Docker Compose and LocalStack can verify batching, persisted state, the real Gateway
to SQS hop, dry-run cost protection, reports, retries, and DLQ wiring locally.
The EventBridge schedules, Fargate task launch, CloudWatch alarms, IAM policies, and
AWS DLQ behavior remain unexecuted until the Terraform is applied in AWS staging.
Terraform validation proves configuration shape, not deployed behavior.
