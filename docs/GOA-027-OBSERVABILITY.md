# GOA-027 observability decisions and verification

## Decisions

### Langfuse hosting and SDK

GOA uses the managed Langfuse Cloud project **GOA** at
`https://cloud.langfuse.com`. `langfuse.goa.app` was not provisioned: the
repository contains neither a Langfuse deployment nor DNS/TLS ownership for
that host. Python tracing is standardized on `langfuse>=4,<5`; Speaking keeps
the documented ingestion HTTP protocol because there is no Go SDK in this
stack.

Cross-service handoffs use a W3C `traceparent`. Orchestration emits it as an
HTTP header for RAG and Writing, and as a query parameter for browser-created
WebSocket/SSE connections, whose native browser APIs cannot set arbitrary
headers. The Gateway converts the Writing query value back to an upstream
header. Missing or malformed values start a safe local trace and never fail a
business request.

### Cost endpoint and store

`GET /admin/costs` remains on the Gateway. The Gateway owns the external admin
boundary and Redis database 0; Orchestration is only one of five cost writers
and has no privileged cost-data view. The canonical Sprint 3 ticket text was
amended to record this decision.

Required roll-ups use:

```text
llm:tokens:{UTC date}:user:{userId}:{service}  hash{input,output}  TTL 35d
llm:tokens:{UTC date}:global                   hash{input,output}  TTL 35d
```

Companion `:model:{base64url model}` hashes preserve the model dimension. The
Gateway applies `LLM_PRICING_JSON` when reading the day and falls back to the
legacy flat price only for an unlisted model. All writers reuse a process-wide
Redis client and set expiry with `EXPIRE NX`.

### CloudWatch publication boundary

Terraform defines the **GOA-Overview** staging dashboard and the ticket's alarm
families. AWS-native Lambda, SQS, and ECS widgets/alarms receive data once the
staging resources exist.

The custom `GOA/Services` widgets and alarms are intentionally documented as
**inert until GOA-021 installs the CloudWatch agent/Prometheus-to-CloudWatch
publication path**. This repository currently contains no `PutMetricData`,
Embedded Metric Format, or CloudWatch agent. Creating panels is not evidence
of published metrics. Latency and error-rate alarms use
`treat_missing_data = "missing"` so absent publication is not reported as a
healthy datapoint.

No AWS credentials were available for this implementation. Terraform was not
applied; the alarms have never entered `ALARM`; SNS email delivery was not
claimed or tested.

Langfuse Cloud does not currently expose the ticket's requested "daily LLM
cost summary email." Its spend-alert email monitors the Langfuse subscription
invoice rather than observed model cost, while project cost monitors notify
through automations such as Slack or webhooks. No unrelated billing alert was
enabled and misrepresented as an LLM-cost summary. See the official
[spend-alert documentation](https://langfuse.com/docs/administration/spend-alerts)
and [monitor documentation](https://langfuse.com/docs/metrics/features/monitors).

### Local scrape and alert audit

Prometheus scrapes Gateway, RAG, Orchestration, Speaking, Writing, and Exam.
The four omitted services do not currently expose scrapeable HTTP metrics:

- User is a NestJS service with no Prometheus endpoint.
- Notification is a Lambda/local worker with no Prometheus endpoint.
- Speech is FastAPI but has no metrics instrumentation or `/metrics`.
- Ingestion declares in-process counters for batch runs but has no HTTP server
  that can expose them.

No fake scrape targets were added. Prometheus evaluates the checked-in alert
rules, but Compose contains no Alertmanager, so local notification delivery is
not claimed.

The Gateway rate-limit counter no longer labels by `user_id`; this removes an
unbounded-cardinality identity label while preserving the aggregate signal.

## Verification snapshot — 2026-07-30

- Langfuse trace `bafaf139219070f41e94356d66ba37e0` contains 26 observations
  under one trace ID, including
  `chat_request → downstream_call → rag-query → retrieval/answer-generation`.
  The traced answer generation records model `claude-opus-4-8`, 3,876 input
  tokens, 194 output tokens, and a non-zero trace cost. The API-derived
  parent/child evidence is in
  `docs/evidence/GOA-027-langfuse-post-fix.json`.
- Admin checks returned `401` with no key, `401` with a wrong key, and `200`
  with the configured key.
- A five-write cost fixture produced `$0.0214` for one user with 1,520 RAG,
  3,500 Writing, and 900 Speaking tokens. The global key TTL was 3,023,989
  seconds immediately after the run (35 days minus elapsed seconds).
- Grafana's API loaded the provisioned dashboard with 19 panels. A live
  WebSocket made `goa_speaking_active_connections` equal `1` in Prometheus. A
  Writing evaluation produced a non-zero p95 value of `19,750 ms`.
- Speaking p95 has a valid scraped histogram series but remained zero because
  no additional quota-sensitive audio/LLM/TTS run was manufactured solely to
  move a chart.
- Both the observability module and root `terraform validate` pass. The root
  check initially exposed obsolete task/service resources left behind in
  `modules/ecs-cluster` after the checked-in state moves transferred ownership
  to `modules/ecs-service`; those duplicate definitions were removed so the
  existing migration and the root configuration agree.
