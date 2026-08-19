# Cambridge IELTS Ingestion Pipeline

## Overview

The ingestion pipeline converts scanned Cambridge IELTS PDFs into structured question data in PostgreSQL. It is split into four independent stages so that expensive operations (OCR) are never repeated unnecessarily.

```
PDF ──► Stage 1: OCR ──► TXT ──► Stage 2: Parse ──► JSON ──► Stage 3: Ingest ──► PostgreSQL
                                                      │
                                                      ▼
                                               Stage 4: Validate ──► Report
```

**Key principle**: JSON is the source of truth. Once a book is OCR'd, you never OCR it again unless the PDF changes. Parser improvements only re-run Stage 2 (seconds). Schema or loading changes only re-run Stage 3 (milliseconds).

---

## Stages

### Stage 1 — OCR (`scripts/ocr_books.py`)

Extracts text from scanned PDFs using pdfplumber with an automatic OCR fallback (pytesseract + pdf2image) for image-only pages.

```
Input:   data/sample_books/**/*.pdf
Output:  data/ocr/<BookSlug>/full.txt
         data/ocr/<BookSlug>/full.sha256
```

- Skips books whose PDF has not changed (compares SHA-256 hash in the sidecar file).
- Resumable — each book is independent; a crash mid-run does not lose progress on completed books.
- This is the slowest stage (minutes per book). Run it once per PDF.

### Stage 2 — Parse (`scripts/parse_books.py`)

Reads OCR text, splits it into per-test blocks, and runs the appropriate skill parser (`ReadingParser`, `ListeningParser`, `WritingParser`, `SpeakingParser`). Writes normalized JSON.

```
Input:   data/ocr/<BookSlug>/full.txt
Output:  data/parsed/<BookSlug>/metadata.json
         data/parsed/<BookSlug>/reading/test1.json
         data/parsed/<BookSlug>/reading/test2.json
         data/parsed/<BookSlug>/listening/test1.json
         data/parsed/<BookSlug>/writing/test1.json
         data/parsed/<BookSlug>/speaking/test1.json
         ...
```

- No OCR code. No database code.
- Skips books whose source text hash has not changed (unless `--force`).
- Fast — typically completes in under a second per book.

### Stage 3 — Ingest (`scripts/ingest_books.py`)

Loads parsed JSON files and inserts them into PostgreSQL using `QuestionRepository.upsert_question()`.

```
Input:   data/parsed/<BookSlug>/<skill>/test<N>.json
Output:  PostgreSQL `questions` table rows
```

- Idempotent — the `(book_ref, test_number, skill_area)` unique constraint prevents duplicates.
- No OCR code. No parser code.

### Stage 4 — Validate (`scripts/validate_books.py`)

Checks parsed JSON for structural correctness and generates a pass/fail report.

| Skill     | Checks                                                                  |
| --------- | ----------------------------------------------------------------------- |
| Reading   | 3 passages, 40 questions, 40 answer keys, no duplicate question numbers |
| Listening | 4 sections, 40 questions, audio S3 key present                          |
| Writing   | 2 tasks (Task 1 + Task 2), prompts > 20 chars                           |
| Speaking  | Parts 1, 2, 3 present; Part 2 has bullet points                         |
| All       | `book_ref`, `test_number`, `exam_type`, `skill_area` present            |

Use `--strict` to enforce exact counts (e.g. exactly 40 questions, exactly 40 answer keys).

---

## Directory Layout

```
services/exam/
├── data/
│   ├── sample_books/              ← Source PDFs (input)
│   │   ├── IELTS 14 Academic/
│   │   │   ├── Cambridge IELTS 14.pdf
│   │   │   └── Audio/
│   │   ├── IELTS 15 Academic/
│   │   └── ...
│   ├── ocr/                       ← Stage 1 output
│   │   ├── IELTS14/
│   │   │   ├── full.txt
│   │   │   └── full.sha256
│   │   ├── IELTS15/
│   │   └── ...
│   └── parsed/                    ← Stage 2 output (source of truth)
│       ├── IELTS14/
│       │   ├── metadata.json
│       │   ├── reading/
│       │   │   ├── test1.json
│       │   │   ├── test2.json
│       │   │   ├── test3.json
│       │   │   └── test4.json
│       │   ├── listening/
│       │   ├── writing/
│       │   └── speaking/
│       └── IELTS15/
├── scripts/
│   ├── ocr_books.py               ← Stage 1
│   ├── parse_books.py             ← Stage 2
│   ├── ingest_books.py            ← Stage 3
│   ├── validate_books.py          ← Stage 4
│   └── pipeline.py                ← Orchestrator
└── app/ingestion/
    ├── ocr_service.py             ← Shared OCR service
    ├── pipeline_config.py         ← Shared paths and helpers
    ├── parser.py                  ← BaseParser (delegates OCR to OcrService)
    ├── reading_parser.py
    ├── listening_parser.py
    ├── writing_parser.py
    └── speaking_parser.py
```

---

## Common Commands

### Run the full pipeline

```bash
python scripts/pipeline.py --all
```

### Run a single stage

```bash
python scripts/pipeline.py --stage ocr
python scripts/pipeline.py --stage parse
python scripts/pipeline.py --stage ingest
python scripts/pipeline.py --stage validate
```

### Filter by book, skil

# Parse only reading for IELTS 14, test 1

python scripts/parse_books.py --book IELTS14 --skill reading --test 1

# Ingest only listening

python scripts/ingest_books.py --skill listening

# Validate one specific file

python scripts/validate_books.py --book IELTS14 --skill reading --test 1

````

### Dry run ingestion

```bash
python scripts/ingest_books.py --dry-run
````

### Force re-processing

```bash
# Re-OCR a book even if the PDF hash has not changed
python scripts/ocr_books.py --book IELTS14 --force

# Re-parse even if the source text hash has not changed
python scripts/parse_books.py --book IELTS14 --force
```

### Strict validation

```bash
python scripts/validate_books.py --strict
```

---

## Adding a New Cambridge Book

1. **Place the PDF** in `data/sample_books/`:

   ```
   data/sample_books/IELTS 20 Academic/Cambridge IELTS 20.pdf
   ```

   The directory name must contain "IELTS" followed by the book number. Audio files go in the same directory or a subdirectory.

2. **Run OCR** (one-time, slow):

   ```bash
   python scripts/ocr_books.py --book IELTS20
   ```

   Verify: `data/ocr/IELTS20/full.txt` exists and contains readable text.

3. **Parse**:

   ```bash
   python scripts/parse_books.py --book IELTS20
   ```

   Verify: JSON files appear under `data/parsed/IELTS20/<skill>/test<N>.json`.

4. **Validate**:

   ```bash
   python scripts/validate_books.py --book IELTS20
   ```

   Fix any parser issues and re-run Stage 2 until all checks pass.

5. **Ingest**:

   ```bash
   python scripts/ingest_books.py --book IELTS20
   ```

6. **Verify in DB** (optional):
   ```bash
   python scripts/e2e_db_verify.py
   ```

---

## Recovering from Failures

### Parser bug — re-parse without OCR

The OCR text is already on disk. Fix the parser, then:

```bash
python scripts/parse_books.py --book IELTS14 --force
python scripts/validate_books.py --book IELTS14
python scripts/ingest_books.py --book IELTS14
```

Total time: seconds.

### OCR produced bad text

Delete the OCR output and re-run:

```bash
rm -rf data/ocr/IELTS14/
python scripts/ocr_books.py --book IELTS14
python scripts/parse_books.py --book IELTS14 --force
```

### Database needs to be rebuilt

The parsed JSON files are the source of truth. Wipe the DB and re-ingest:

```bash
python scripts/ingest_books.py --force
```

Or for a single book:

```bash
python scripts/ingest_books.py --book IELTS14
```

The `ON CONFLICT DO NOTHING` constraint makes this safe to run repeatedly.

### Stage failed mid-run

Every stage processes books independently. Re-run the same command — completed books are skipped (by hash check or DB idempotency), and the failed book retries.

---

## Architecture Notes

- **OcrService** (`app/ingestion/ocr_service.py`) is the single OCR implementation. Both `BaseParser.parse_pdf()` (used by the FastAPI app) and `scripts/ocr_books.py` (used by the pipeline) delegate to it. One place to fix bugs.
- **Parsers are unchanged**. `ReadingParser`, `ListeningParser`, `WritingParser`, and `SpeakingParser` still expose `parse_text(content)` and `parse_pdf(path)`. The pipeline calls `parse_text()` only.
- **QuestionRepository is unchanged**. `ingest_books.py` calls `upsert_question()` exactly as the FastAPI app does.
- **Tests are unaffected**. All 65 existing tests pass without modification to parsing or repository logic.
