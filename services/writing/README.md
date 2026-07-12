# GOA Writing Service

The Writing service owns essay text and CV file receipt. GOA-089 adds `POST /cv/upload`; CV extraction remains the responsibility of GOA-087.

## CV upload

Send an authenticated multipart request through the Gateway:

```bash
curl -X POST http://localhost:8080/cv/upload \
  -H "Authorization: Bearer <jwt>" \
  -F "userId=<jwt-subject>" \
  -F "file=@resume.pdf;type=application/pdf"
```

The endpoint accepts PDF, DOC, and DOCX files up to exactly 10 MB. It returns `202` with `{ "cvId": ..., "status": "processing" }`. Files are stored in `goa-writing-files` under `cvs/{userId}/{uuid}.{ext}`.

S3 sends `ObjectCreated` notifications for `cvs/` to `goa-cv-processing`, which GOA-087 consumes. The service separately publishes the GOA-002 `cv.uploaded` domain event to `goa-cv-uploaded`.

## Configuration

Copy `.env.example` and configure:

- `DATABASE_URL`
- `AWS_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_ENDPOINT_URL` for LocalStack development
- `S3_BUCKET`
- `CV_UPLOADED_QUEUE_URL`

No internal API key is used for this user-facing route. The Gateway verifies the JWT and requires the multipart `userId` to match the authenticated subject.

## Local development

From the repository root:

```bash
docker compose up -d postgres localstack writing gateway
```

The Writing container applies the SQL migrations before starting on port `8000`. LocalStack bootstrap creates the bucket, domain queue, processor queue, SQS policy, and filtered S3 notification.

## Tests

```bash
cd services/writing
python -m pip install -r requirements.txt
python -m pytest -q
```

The LocalStack/PostgreSQL integration test is opt-in:

```bash
RUN_WRITING_INTEGRATION=1 python -m pytest tests/integration -q
```

Set `DATABASE_URL`, `AWS_ENDPOINT_URL`, and `CV_UPLOADED_QUEUE_URL` to the host-accessible development resources first. Set `RUN_CV_PROCESSOR_E2E=1` only when GOA-087 is running; that additionally verifies the `processing` to `ready` transition.
