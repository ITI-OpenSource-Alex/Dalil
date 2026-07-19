# OCR Normalization

## Overview

The OCR normalization layer is a deterministic, domain-agnostic text-cleaning module that runs as the first processing stage after loading raw OCR text files. It repairs common OCR artifacts without any knowledge of IELTS document structure.

## Architecture Position

```
OCR PDF
    ↓
OCRNormalizer.normalize()       ← this module
    ↓
Test Splitter
    ↓
Parser (uses parser_helpers.py for semantic disambiguation)
    ↓
Validator
```

## Module: `app/ingestion/ocr_normalizer.py`

### Usage

```python
from app.ingestion.ocr_normalizer import DEFAULT_NORMALIZER

raw_text = path.read_text(encoding="utf-8")
clean_text = DEFAULT_NORMALIZER.normalize(raw_text)
```

### Pipeline

The normalizer applies these functions in order:

| Step | Function                   | Purpose                                                         |
| ---- | -------------------------- | --------------------------------------------------------------- |
| 1    | `normalize_unicode`        | NFC normalization, remove zero-width chars, NBSP → space        |
| 2    | `normalize_dashes`         | Em-dash, en-dash, minus sign → hyphen                           |
| 3    | `normalize_quotes`         | Curly quotes → straight quotes                                  |
| 4    | `normalize_ellipsis`       | `…` → `...`                                                     |
| 5    | `remove_page_footers`      | Strip lines matching OCR page footer patterns                   |
| 6    | `remove_publisher_headers` | Strip lines starting with "Cambridge IELTS/University Press"    |
| 7    | `remove_copyright`         | Strip lines containing © or "Copyright"                         |
| 8    | `remove_page_numbers`      | Strip lines that are only 1-3 digits                            |
| 9    | `normalize_bullets`        | Various bullet chars at line start → `•`                        |
| 10   | `normalize_whitespace`     | Collapse inline multi-space/tabs → single space, strip trailing |
| 11   | `collapse_blank_lines`     | 3+ consecutive blank lines → 2                                  |

Every function is:

- Pure (`str → str`)
- Independent (no shared state)
- Deterministic (same input always produces same output)
- Domain-agnostic (no IELTS knowledge)

### Adding New Rules

1. Write a function: `def my_new_rule(text: str) -> str`
2. Add a unit test in `tests/test_ocr_normalizer.py`
3. Insert it into `OCRNormalizer._PIPELINE` at the appropriate position
4. Verify idempotence (running twice produces the same result)

### Constraints

The normalizer must NOT:

- Interpret document structure (passages, questions, tests)
- Apply heuristic repairs that could be wrong
- Contain any book-specific logic
- Know what IELTS is

---

## Module: `app/ingestion/parser_helpers.py`

Stateless utility functions that resolve OCR ambiguities requiring structural context. The parser calls these only when it knows the surrounding context.

### Functions

#### `parse_question_range(raw: str) -> QuestionRangeParse | None`

Given a raw number string (e.g., `"1428"`), returns all valid ways to split it into `(start, end)` where `start < end`.

```python
parse_question_range("1428")
# QuestionRangeParse(candidates=[(1, 428), (14, 28)], ambiguous=True)

parse_question_range("123")
# QuestionRangeParse(candidates=[(1, 23)], ambiguous=False)

parse_question_range("abc")
# None
```

The parser decides which candidate is correct based on its position in the document.

#### `parse_passage_header(line: str) -> PassageHeader | None`

Given a line that might be a passage header, extracts the raw number and all non-zero digits as candidates.

```python
parse_passage_header("READING PASSAGE 74")
# PassageHeader(raw_number=74, candidates=[7, 4])

parse_passage_header("READING PASSAGE 2")
# PassageHeader(raw_number=2, candidates=[2])
```

The parser decides which candidate is the actual passage number.

#### `classify_test_marker(line: str) -> TestMarker | None`

Classifies a line as a potential test boundary marker.

```python
classify_test_marker("Test 1")
# TestMarker(test_number=1, is_toc=False, is_phantom=False)

classify_test_marker("Test 1 10")
# TestMarker(test_number=1, is_toc=True, is_phantom=False)

classify_test_marker("Test 7")
# TestMarker(test_number=7, is_toc=False, is_phantom=True)
```

The parser decides whether to use or discard the marker.

---

## Design Principles

1. **Normalizer answers**: "How can I clean this text?"
2. **Parser helpers answer**: "What are the possible interpretations?"
3. **Parser answers**: "What does this text mean?"

This separation ensures:

- The normalizer is reusable for any OCR project
- Parser helpers never guess — they return candidates
- The parser owns all semantic decisions

## Parser Debugging

To manually inspect the intermediate text at every major stage of parsing, you can run the parsing script with the optional `--debug` flag:

```bash
python scripts/parse_books.py --debug
```

When this flag is provided, the parser creates a `debug/` directory (e.g., `debug/IELTS14/test1/`) and writes out plain text files for each stage:

* `01_test_block.txt`
* `02_reading_section.txt`
* `03_passages.txt`
* `04_questions.txt`
* `05_answers.txt`

**Note:**
* This flag exists **only for parser investigation** and observability.
* It **does not affect production behavior** or change the output JSON in any way.
* When omitted, the parser behaves exactly as it normally does.
