# GOA-087 — CV Processor Lambda

## Outcome

GOA-087 adds an asynchronous Writing worker that turns a CV uploaded beneath
`cvs/{userId}/` into plain text and validated structured data. The worker stores the
result in `writing_db.cv_reviews` and publishes a `CVProcessed` event containing the
durable CV record identifier and final status.

The production entrypoint is:

```text
cv_processor.handler.lambda_handler
```

Local development uses the same processor through `cv_processor.local_worker`, which
polls the LocalStack `goa-cv-processing` queue populated by the filtered S3
notification.

## Processing flow

1. Decode each S3 `ObjectCreated` record and require a `cvs/{userId}/...` key.
2. Call `HeadObject` before downloading to enforce the 10 MB limit.
3. Detect PDF or DOCX from the extension and content type. Other types become durable
   `failed` reviews and do not crash the invocation.
4. Compare the S3 `sha256` metadata with a ready row. A match is skipped before both
   download and LLM execution. For objects without hash metadata, compute SHA-256 after
   download and perform the same ready-row check before the LLM call. The review row is
   locked through extraction so concurrent deliveries serialize around this check.
5. Extract text with `pdfplumber` or `python-docx`.
6. Ask `claude-haiku-4-5-20251001` for the strict CV JSON schema. Invalid JSON/schema
   output is retried once.
7. Persist `extracted_text`, `structured_data`, `content_hash`, final status,
   `error_message`, and `processed_at`.
8. Publish `CVProcessed` to `CV_PROCESSED_QUEUE_URL`.

If `ANTHROPIC_API_KEY` is absent, the Lambda fails before claiming or mutating a CV
review. AWS retries the asynchronous S3 invocation twice, then sends the original
invocation payload to the 14-day `goa-cv-processor-failures-{environment}` queue. This
prevents an infrastructure configuration problem from becoming a permanent user-level
`failed` extraction record.

The structured schema contains `name`, `email`, `phone`, `degree`, `institution`,
`graduation_year`, `field_of_study`, `skills`, `work_experience`, and `languages`.
Unknown scalar values are `null`; unknown collections are empty arrays.

## Event contract

`CVProcessed` retains the GOA-002 base event envelope (`version`, `timestamp`, and
`correlationId`) and adds these fields:

```json
{
  "type": "CVProcessed",
  "version": "1.0",
  "timestamp": "2026-07-18T12:00:00Z",
  "correlationId": "s3-request-id",
  "userId": "user-123",
  "cvId": 42,
  "s3Key": "cvs/user-123/resume.pdf",
  "status": "ready"
}
```

`status` is `ready` or `failed`. Extracted CV content is deliberately not copied into
SQS; consumers retrieve it from `cv_reviews` using `cvId`.

## Persistence

Migration `004_add_cv_processor_fields.sql` adds:

- `content_hash VARCHAR(64)`
- `extracted_text TEXT`
- `structured_data JSONB`
- `error_message TEXT`
- `processed_at TIMESTAMPTZ`

The existing `s3_key` uniqueness constraint remains. Replacing an object at the same
key with different content reprocesses the existing review; redelivering identical
content does not spend a second LLM call. A skipped retry republishes the ready event so
a transient SQS failure after the database commit is recoverable; consumers therefore
handle `CVProcessed` with normal at-least-once semantics.

## Observability

- `goa_cv_extraction_duration_ms` records end-to-end worker duration.
- `goa_cv_extraction_total{outcome="success|fail|skipped"}` records outcomes.
- Each invocation emits one JSON log with `userId`, `cvId`, `file_type`, `text_length`,
  `fields_extracted`, `duration_ms`, and `outcome`.
- The structured call records a Langfuse trace containing model, token counts, latency,
  estimated cost, and fields extracted. CV text is redacted from the trace.
- Terraform retains the Lambda log group for 30 days and alarms through the shared SNS
  topic when the asynchronous invocation-failure queue contains any message.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Writing PostgreSQL connection | local Writing database |
| `S3_BUCKET` | CV object bucket | `goa-writing-files` |
| `CV_PROCESSOR_QUEUE_URL` | Local S3-notification queue | empty |
| `CV_PROCESSED_QUEUE_URL` | Completed-event destination | empty (required) |
| `CV_EXTRACTION_MODEL` | Structured extraction model | `claude-haiku-4-5-20251001` |
| `ANTHROPIC_API_KEY` | Claude credential | empty |
| `WRITING_SECRET_ARN` | Production Writing JSON secret | empty |
| `LANGFUSE_*` | Optional tracing credentials and host | empty/default host |

The Lambda reads the existing Writing Secrets Manager JSON before importing the
database engine. The Terraform image override starts `awslambdaric` with the handler,
and the Lambda role can read the Writing bucket, Writing secret, processed queue, and
failure destination queue.

## Local validation

```bash
docker compose up -d postgres localstack writing cv-processor
cd services/writing
python -m pytest tests/unit/test_cv_processor.py -q
```

With an Anthropic key configured, uploading a real PDF or DOCX through `POST /cv/upload`
causes the local worker to transition the row from `processing` to `ready` and publish
to `goa-cv-processed`.

After restoring a missing production credential, inspect and then replay retained
asynchronous failures:

```bash
python services/writing/scripts/replay_cv_processor_failures.py \
  --queue-url <failure-queue-url> \
  --function-name goa-cv-processor-production

python services/writing/scripts/replay_cv_processor_failures.py \
  --queue-url <failure-queue-url> \
  --function-name goa-cv-processor-production \
  --execute
```

The first command is a dry run. `--execute` deletes a failure message only after Lambda
accepts its original S3 payload for asynchronous replay.

## Acceptance matrix

| Requirement | Implementation |
|---|---|
| S3 Lambda handler under `services/writing/cv_processor` | `handler.py` |
| PDF and DOCX text extraction | `extraction.py` |
| Strict structured Claude extraction and one retry | `structured.py` |
| Unsupported/oversized files fail without download crash | `CVProcessor.process_record` |
| Durable text, JSON, status, error, timestamps | migration 004 and `CVReview` |
| `CVProcessed` event | Python/TypeScript contracts and event publisher |
| Same-key/content idempotency | S3 SHA-256 metadata plus database hash check |
| Metrics, JSON log, Langfuse | Writing metrics/observability modules |
| `cvs/` trigger | existing Terraform and LocalStack filters (confirmed) |

GOA-072/GOA-031 infrastructure in this repository already uses the correct `cvs/`
prefix, so no `essays/` trigger correction was necessary. GOA-025 should read the
persisted `extracted_text` and `structured_data` from `cv_reviews` rather than invoke
extractors itself.

## Deployment readiness status

Completed without external model credentials:

- unit suite and mocked structured-output coverage;
- real PostgreSQL migration and schema verification;
- real LocalStack S3 notification, SQS event, JSONB persistence, and idempotency flow;
- Lambda image build and handler import;
- clean Terraform validation and a production-shaped offline plan;
- durable asynchronous failure queue, 30-day Lambda logs, CloudWatch/SNS alarm, and
  dry-run-first replay tooling;
- real AWS credential-chain support (mock credentials are now restricted to explicit
  `aws_offline_mode`).

External values still required before an AWS apply can be executed:

- an AWS credential chain and region;
- the 12-digit AWS account ID;
- the three ECR repository URLs and an immutable image tag;
- the remote-state bucket/lock table created by `infra/terraform/bootstrap.sh`;
- `ANTHROPIC_API_KEY` in the Writing secret. Langfuse keys remain optional.

The production templates now include every missing account, ECR, image, and backend
field. Do not run `apply` with `aws_offline_mode=true` or placeholder values.
