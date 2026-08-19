# Academic Writing Task 1 chart crops

Manual crops for the Academic Writing **Task 1** stimulus (the chart / graph /
map / diagram the candidate must describe) live in this directory. Stage 2 of
the ingestion pipeline (`scripts/parse_books.py`) picks them up automatically.

## Naming convention

Place one PNG per Academic writing test, named:

```
<book-slug>-test<N>-task1.png
```

Examples:

```
IELTS15-test1-task1.png
IELTS18-test4-task1.png
```

- `<book-slug>` is the OCR book slug (e.g. `IELTS15`, no dash).
- `<N>` is the 1-based test number.

## What the parser does

When `parse_books.py` runs for a writing test and finds a matching crop here, it:

1. Uploads it to the `goa-writing-files` S3 bucket (LocalStack in dev) under the
   deterministic key `charts/<book_ref>-test-<N>-task1.png`
   (e.g. `charts/IELTS-15-test-1-task1.png` — note `book_ref` uses the dashed
   form `IELTS-15`).
2. Records that key at the root of the parsed JSON as `image_s3_key`, alongside
   how Listening records `audio_s3_key`.

## Idempotent by design

- **General Training** Task 1 is a letter with no stimulus image, so no crop is
  placed here and the test is left with no `image_s3_key` — nothing to do.
- Any Academic test not yet cropped is likewise skipped until its crop is added.
- Re-running the parser overwrites the same deterministic S3 key, so repeated
  runs are safe.

Crops themselves are **not** committed to the repo (see `.gitignore`); only this
README is tracked.
