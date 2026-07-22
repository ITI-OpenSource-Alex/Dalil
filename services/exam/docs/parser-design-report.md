# Parser Design Report: Generalized Cambridge IELTS Parser

> **Goal**: Design a parser that generalizes to any Cambridge IELTS Academic book (past and future) by relying on structural invariants of the exam format, not on OCR artifacts of specific books.

---

## 1. Structural Anchors (Ranked Strongest → Weakest)

Every Cambridge IELTS Academic book follows a fixed exam structure. The anchors below are properties of the **exam format itself**, not of any particular PDF or OCR output.

| Rank | Anchor | Type | Why It's Strong | Regex Pattern |
|------|--------|------|-----------------|---------------|
| 1 | `Questions X–Y` headers | Corpus-driven | Present before every question block in every skill. Defines exact question number ranges. Never appears in passage prose. | `(?i)questions?\s*(\d{1,2})\s*[-–—_to~and\s]+(\d{1,2})` |
| 2 | Question numbering (1–40) | Corpus-driven | Every test has exactly 40 questions numbered sequentially. Numbering resets per test. This is an exam-format invariant. | `^(\d{1,2})[.)]\s+` or inline `(\d{1,2})\s*[._]{2,}` |
| 3 | "You should spend about 20 minutes" | Corpus-driven | Appears at the start of every reading passage in every Cambridge book. The single most reliable passage delimiter. | `(?i)you should spend about \d+ minutes` |
| 4 | Task/completion instructions | Corpus-driven | Fixed vocabulary: "Complete the notes/summary/table/sentences below", "Choose the correct letter", "Do the following statements agree", "Write ONE WORD". | `(?i)(complete the|choose the correct|do the following|write (one|no more than))` |
| 5 | `READING PASSAGE N` header | Corpus-driven | Marks passage boundaries. Always present in the source PDF — OCR may corrupt the number but the phrase "READING PASSAGE" persists. | `(?i)reading\s+passage\s+(\d+)` |
| 6 | Skill transition keywords | Corpus-driven | `READING`, `WRITING`, `SPEAKING`, `LISTENING` as section headers. The exam always presents skills in this fixed order per test. | `(?i)^(READING|WRITING|SPEAKING|LISTENING)\b` |
| 7 | `Test N` boundary | Corpus-driven | Each book contains exactly 4 tests. The marker exists in the PDF — OCR may lose it, but the structural expectation is fixed. | `(?i)^test\s+(\d)\b` |
| 8 | Answer key region | Corpus-driven | Always appears after all test content. Contains numbered answers organized by skill/passage. | `(?i)^(answer\s*key|answers?)` combined with numbered entries |
| 9 | Writing Task markers | Corpus-driven | `WRITING TASK 1` and `WRITING TASK 2` — fixed exam structure. | `(?i)writing\s+task\s+([12])` |
| 10 | Speaking Part markers | Corpus-driven | `PART 1`, `PART 2`, `PART 3` within speaking sections. | `(?i)part\s+([123])` |

### Classification: Corpus-Driven vs OCR-Driven

- **Corpus-driven anchors** (1–10 above): Properties of the Cambridge IELTS exam format. They exist in every correctly printed book. A parser built on these will work on IELTS 18, 20, 21+ without modification.
- **OCR-driven observations**: Things like "IELTS16 has no Test 2 marker" or "IELTS14 uses SECTION not PART" are artifacts of OCR quality or edition-specific typography. The parser should NOT branch on these. Instead, it should attempt recovery when an expected corpus-driven anchor is missing.

---

## 2. Normalization Layer

Before any parsing, the raw OCR text must pass through a normalization pipeline that repairs known OCR corruption classes. These are **generic text-repair operations**, not book-specific patches.

### 2.1 Normalization Operations (in order)

```
Raw OCR Text
    │
    ▼
┌─────────────────────────────────────┐
│ 1. Line-level cleanup               │
│    - Strip page footers             │
│    - Strip copyright lines          │
│    - Strip page numbers             │
│    - Collapse multiple blank lines  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ 2. Character-level repair           │
│    - Normalize Unicode dashes       │
│    - Normalize quote variants       │
│    - Fix common OCR substitutions   │
│    - Normalize whitespace           │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ 3. Structural repair                │
│    - Repair merged question ranges  │
│    - Repair corrupted passage nums  │
│    - Repair split/merged lines      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│ 4. Zone detection                   │
│    - Mark answer-key region         │
│    - Mark sample-writing region     │
│    - Mark front-matter/TOC region   │
└──────────────┬──────────────────────┘
               │
               ▼
           Normalized Text
```

### 2.2 Specific Repairs

| Corruption Class | Example | Repair Rule | Type |
|-----------------|---------|-------------|------|
| Missing dash in question range | `Questions 1428` (should be `14–28`) | If a "Questions" header has a single number > 40, split at the boundary where left ≤ 40 and right > left | OCR-driven |
| Corrupted passage number | `READING PASSAGE 74` | Any passage number > 3 → extract last digit, clamp to 1–3 | OCR-driven |
| Unicode dash variants | `–`, `—`, `−`, `_` used as range separator | Normalize all to `–` in question-range context | OCR-driven |
| Page footers | `> [Q p. 123 p. 107]`, `Cambridge IELTS 14` | Strip lines matching footer patterns: `^[>\d\s]*\[?[QSB]?\s*p\.` and `^Cambridge\s+IELTS` | OCR-driven |
| Merged lines | Two questions on one line | If a line contains two `N.` patterns, split into separate lines | OCR-driven |
| Bullet normalization | `*`, `•`, `·`, `►`, `-` as bullets | Normalize all to `•` | OCR-driven |
| Spurious "Test N" in prose | "Test 7 was conducted on..." | Only accept `Test N` on its own line (no trailing prose beyond a page number) | OCR-driven |
| Section/Part equivalence | `SECTION 1` vs `PART 1` | Treat both as equivalent listening division markers | Corpus-driven (format evolution) |
| Score band tables | "If you score 30–32..." | Detect and strip lines matching score-band patterns | OCR-driven |
| Trailing page numbers on TOC lines | `Test 1 10` | In TOC zone only: strip trailing bare numbers | OCR-driven |

### 2.3 Design Principle

The normalization layer is a **pure function**: `normalize(raw_text) → clean_text`. It has no knowledge of parser state, question types, or skill areas. It operates only on text patterns that are unambiguously OCR noise or corruption. When in doubt, it preserves the original text — false normalization is worse than leaving noise for the parser to handle.

---

## 3. State Machine Architecture

### 3.1 Why a State Machine?

The current parser uses isolated regex passes that each scan the full text independently. This causes:
- False matches (passage text interpreted as questions)
- Lost context (no awareness of which zone we're in)
- Book-specific patches (because context-free regexes can't distinguish structural zones)

A state machine processes text **line by line** with full awareness of the current structural context. Each line is interpreted relative to the current state, eliminating false matches from wrong zones.

### 3.2 State Hierarchy

```
┌──────────────────────────────────────────────────────────────┐
│                        DOCUMENT                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────┐│
│  │ FRONT_MATTER│  │TEST_CONTENT│  │ ANSWER_KEYS│  │APPENDIX││
│  └────────────┘  └─────┬──────┘  └─────┬──────┘  └────────┘│
│                        │               │                     │
└────────────────────────┼───────────────┼─────────────────────┘
                         │               │
           ┌─────────────▼──────┐  ┌─────▼──────────────────┐
           │        TEST        │  │   ANSWER_KEY_BLOCK     │
           │  ┌──────────────┐  │  │  (per test, per skill) │
           │  │  LISTENING   │  │  └────────────────────────┘
           │  ├──────────────┤  │
           │  │   READING    │  │
           │  ├──────────────┤  │
           │  │   WRITING    │  │
           │  ├──────────────┤  │
           │  │  SPEAKING    │  │
           │  └──────────────┘  │
           └────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
    ▼               ▼               ▼
┌────────┐   ┌──────────┐   ┌──────────────┐
│PASSAGE │   │  SECTION │   │    TASK      │
│(Reading)│   │(Listening)│   │(Writing/Speak)│
└───┬────┘   └────┬─────┘   └──────────────┘
    │              │
    ▼              ▼
┌──────────────────────┐
│    QUESTION_BLOCK    │
│  (Questions X–Y)     │
│  ┌────────────────┐  │
│  │   QUESTION     │  │
│  │  (individual)  │  │
│  └────────────────┘  │
└──────────────────────┘
```

### 3.3 State Transitions

```python
# Pseudocode — each state defines:
#   - entry_signals: what triggers transition INTO this state
#   - exit_signals: what triggers transition OUT of this state
#   - line_handler: what to do with each line while in this state

STATES = {
    "DOCUMENT": {
        "entry": "start of file",
        "children": ["FRONT_MATTER", "TEST", "ANSWER_KEYS", "APPENDIX"],
        "transitions": {
            "→ FRONT_MATTER": "default initial state",
            "→ TEST": "Test N marker OR first skill header after front-matter",
            "→ ANSWER_KEYS": "answer key header detected",
            "→ APPENDIX": "sample writing / score tables after answer keys",
        }
    },

    "FRONT_MATTER": {
        "entry": "start of document",
        "exit": "first Test marker OR first skill-section header",
        "action": "discard (TOC, acknowledgments, intro)"
    },

    "TEST": {
        "entry": "Test N marker (on own line, N in 1–4)",
        "exit": "next Test marker OR answer-key region",
        "children": ["LISTENING", "READING", "WRITING", "SPEAKING"],
        "invariant": "exactly 4 tests per document",
        "transitions": {
            "→ LISTENING": "PART/SECTION header OR listening instruction",
            "→ READING": "READING header OR 'You should spend...' marker",
            "→ WRITING": "WRITING header OR WRITING TASK marker",
            "→ SPEAKING": "SPEAKING header OR speaking Part 1 marker",
        }
    },

    "READING": {
        "entry": "READING keyword OR 'You should spend...'",
        "exit": "next skill header (WRITING/SPEAKING/LISTENING) OR next Test marker",
        "children": ["PASSAGE"],
        "invariant": "exactly 3 passages per reading section"
    },

    "PASSAGE": {
        "entry": "'You should spend...' OR 'READING PASSAGE N'",
        "exit": "next passage marker OR skill exit",
        "children": ["PASSAGE_TEXT", "QUESTION_BLOCK"],
        "transitions": {
            "→ PASSAGE_TEXT": "default after entry (prose content)",
            "→ QUESTION_BLOCK": "'Questions X–Y' header detected",
        }
    },

    "QUESTION_BLOCK": {
        "entry": "'Questions X–Y' header",
        "exit": "next 'Questions X–Y' header OR passage/skill boundary",
        "contains": "instruction line + individual questions",
        "children": ["QUESTION"]
    },

    "QUESTION": {
        "entry": "numbered line matching expected range",
        "exit": "next numbered line OR block boundary",
        "action": "accumulate prompt text"
    },

    "ANSWER_KEYS": {
        "entry": "'Answer key' / 'Answers' header after all tests",
        "exit": "end of file OR appendix marker",
        "action": "extract numbered answers, associate with test/skill"
    }
}
```

### 3.4 Recovery Mechanisms

When an expected transition signal is missing (OCR dropped it), the state machine uses **fallback heuristics**:

| Expected Signal | Fallback When Missing | Confidence |
|----------------|----------------------|------------|
| `Test N` marker | Infer test boundary from skill-sequence reset (Listening appearing after Speaking) | MEDIUM |
| `READING` header | First "You should spend..." after Listening content ends | HIGH |
| `READING PASSAGE N` | "You should spend..." as passage delimiter (always present) | HIGH |
| `Questions X–Y` | Numbered lines in expected range after prose content | MEDIUM |
| Skill transition | Question numbering reset to 1 (listening); passage-style prose after numbered questions end | LOW |
| `LISTENING` header | First `PART 1`/`SECTION 1` + `Questions 1–10` after test start | HIGH |

### 3.5 Line Classification

Every line is classified before state-transition logic runs:

```python
class LineType(Enum):
    TEST_BOUNDARY = "test_boundary"         # ^Test N$
    SKILL_HEADER = "skill_header"           # ^READING$, ^LISTENING$, etc.
    PASSAGE_HEADER = "passage_header"       # READING PASSAGE N
    TIME_MARKER = "time_marker"             # You should spend about...
    QUESTION_RANGE = "question_range"       # Questions X–Y
    INSTRUCTION = "instruction"             # Complete the..., Choose the...
    NUMBERED_LINE = "numbered_line"         # N. text or N) text
    BULLET_LINE = "bullet_line"            # • text
    GAP_LINE = "gap_line"                  # contains inline N___
    OPTION_LINE = "option_line"            # ^[A-H][.)]\s+
    ANSWER_KEY_HEADER = "answer_key_header" # Answer key(s)
    ANSWER_ENTRY = "answer_entry"          # N. answer or N answer
    PROSE = "prose"                         # default — passage text
    NOISE = "noise"                         # footer, copyright, blank
```

Line classification is context-free (based only on the line content). State transitions use classified lines + current state to decide what to do.

---

## 4. Validation Rules

Validation is applied at every stage of the state machine, not just at the end. This catches errors early and provides precise diagnostics.

### 4.1 Document-Level Validation

| Rule | Expected | Recovery |
|------|----------|----------|
| Number of tests | Exactly 4 | If < 4 detected, check for missed boundaries using skill-sequence heuristic |
| Answer key region exists | Yes | If not found, check for alternate headers ("Key", "Answers") |
| No content after appendix marker | Trim | — |

### 4.2 Test-Level Validation

| Rule | Expected | Recovery |
|------|----------|----------|
| Contains all 4 skills | Listening + Reading + Writing + Speaking | Flag missing skills; do not fabricate |
| Skill order | L → R → W → S (standard Cambridge order) | Accept any order but warn if non-standard |
| Total questions across skills | 40 (L) + 40 (R) + 2 (W) + variable (S) | — |

### 4.3 Reading Validation

| Rule | Expected | Recovery |
|------|----------|----------|
| Number of passages | Exactly 3 | If < 3, look for missed "You should spend..." |
| Questions per passage | ~13–14 (sum = 40) | Accept any distribution summing to 40 |
| Total questions | Exactly 40 | Flag if ≠ 40 |
| Total answer keys | Exactly 40 | Flag if ≠ 40 |
| Question numbering | Sequential 1–40, no gaps, no duplicates | If gaps found, re-scan with relaxed patterns |
| Passage text non-empty | > 100 chars per passage | Flag if passage text is suspiciously short |
| Question-answer alignment | Every question number has a matching answer key entry | List orphan questions and orphan answers |

### 4.4 Listening Validation

| Rule | Expected | Recovery |
|------|----------|----------|
| Number of sections/parts | Exactly 4 | Infer from question ranges (1–10, 11–20, 21–30, 31–40) |
| Questions per section | 10 each | Accept variation but warn |
| Total questions | Exactly 40 | — |
| Total answer keys | Exactly 40 | — |
| Question numbering | Sequential 1–40 | — |
| Audio reference | Present (S3 key or placeholder) | Generate placeholder if missing |

### 4.5 Writing Validation

| Rule | Expected | Recovery |
|------|----------|----------|
| Number of tasks | Exactly 2 | — |
| Task 1 prompt length | > 20 chars | Flag if too short (likely extraction failure) |
| Task 2 prompt length | > 20 chars | — |
| Task type detection | Task 1: letter/graph/map/process; Task 2: essay | Warn if unclassified |

### 4.6 Speaking Validation

| Rule | Expected | Recovery |
|------|----------|----------|
| Parts present | 1, 2, 3 | — |
| Part 2 has cue card | Topic + bullet points | — |
| Part 1 has questions | ≥ 3 questions | — |
| Part 3 has questions | ≥ 2 questions | — |

### 4.7 Answer Key Validation

| Rule | Expected | Recovery |
|------|----------|----------|
| Per-skill coverage | 40 reading + 40 listening | — |
| No duplicate numbers | Within each skill | Keep first occurrence, warn on duplicates |
| Number range | 1–40 for reading and listening | Strip entries outside range |
| Answer non-empty | Every answer has content | Flag blanks |

### 4.8 Cross-Validation (Question ↔ Answer Key)

| Rule | Check |
|------|-------|
| Coverage | Every question N in 1–40 has answer_key[N] |
| Reverse coverage | Every answer_key[N] has a corresponding question N |
| Type consistency | If question_type is "Multiple Choice", answer should be a letter A–D |
| Orphan detection | Questions without answers OR answers without questions → diagnostic output |

---

## 5. Generic Heuristics

These heuristics are designed to work on **any** Cambridge IELTS Academic book without book-specific conditions.

### 5.1 Test Boundary Detection

**Primary signal (corpus-driven):** `^Test\s+N$` on its own line where N ∈ {1,2,3,4}.

**Fallback when missing (corpus-driven):** Cambridge IELTS tests always follow the skill sequence Listening → Reading → Writing → Speaking. If the state machine detects a Listening section starting after a Speaking section ended, it infers a new test boundary.

**False-positive filter:** Reject "Test N" if:
- The line has trailing content beyond whitespace (e.g., `Test 1 was conducted...`)
- N > 4 (impossible for Cambridge IELTS Academic)
- The line is inside a detected passage-text zone
- The line is in the answer-key region (uppercase `TEST N` in answer keys is an answer-key sub-header, not a test boundary)

### 5.2 Skill Detection

**Primary signal (corpus-driven):** Explicit skill header on own line: `READING`, `LISTENING`, `WRITING`, `SPEAKING`.

**Fallback signals (corpus-driven):**
- Listening: `PART 1 Questions 1–10` or `SECTION 1 Questions 1–10` (question range starting at 1)
- Reading: `You should spend about 20 minutes` (first occurrence after listening ends)
- Writing: `WRITING TASK 1` or task-1 instruction patterns
- Speaking: `Part 1` after writing content ends, or examiner instruction patterns

**Why these generalize:** The exam format mandates these structural elements. They are not OCR artifacts — they are printed in every Cambridge book. OCR may corrupt their formatting but rarely eliminates them entirely.

### 5.3 Passage Boundary Detection (Reading)

**Primary signal (corpus-driven):** `You should spend about 20 minutes on Questions X–Y, which are based on Reading Passage N`

This sentence appears verbatim (modulo minor OCR noise) at the start of every reading passage in every Cambridge IELTS book. It simultaneously provides:
- Passage number
- Question range for that passage
- Time allocation

**Secondary signal:** `READING PASSAGE N` header (may be corrupted but phrase "READING PASSAGE" is distinctive enough).

**Tertiary signal:** A `Questions X–Y` header where X = previous passage's last question + 1.

### 5.4 Question Block Detection

**Primary signal (corpus-driven):** `Questions X–Y` or `Questions X and Y` header line.

**What it provides:**
- Exact question numbers expected in this block
- Block boundary (next `Questions` header ends the current block)

**Instruction line (corpus-driven):** The line(s) immediately following the `Questions X–Y` header contain the task instruction: "Complete the summary below", "Choose the correct letter", "Do the following statements agree with the information in the passage?", etc.

### 5.5 Question Type Classification

**Heuristic (corpus-driven):** Based on instruction keywords. Cambridge IELTS uses a fixed set of ~12 question types with consistent instruction phrasing:

| Instruction Keywords | Question Type |
|---------------------|---------------|
| "TRUE / FALSE / NOT GIVEN" or "agree with the information" | TFNG |
| "YES / NO / NOT GIVEN" or "agree with the views/claims" | YNNG |
| "Choose the correct letter" | Multiple Choice |
| "Complete the summary/notes/table/sentences/flow-chart" | Completion |
| "Choose TWO letters" | Multiple Selection |
| "match" or "matching" | Matching |
| "label the diagram/map/plan" | Labeling |
| "heading" or "choose the correct heading" | Heading Match |
| "Which paragraph contains" or "which section" | Locating Information |

**Why this generalizes:** Cambridge has used these same question types with nearly identical instruction wording since IELTS 1. The phrasing is part of the exam specification, not a publishing choice.

### 5.6 Question Extraction Strategies

Each question type has a different textual shape. The parser dispatches to a type-specific extractor based on the classified instruction:

| Question Type | Textual Shape | Extraction Strategy |
|---------------|---------------|---------------------|
| TFNG / YNNG | Statements (one per line, may lack numbers) | Collect lines that start with a capital letter and contain > 3 words; assign numbers sequentially within expected range |
| Multiple Choice | Numbered stem + lettered options (A/B/C/D) | Match numbered line as stem, collect A–D option lines until next stem |
| Completion (notes/table) | Structured layout with inline gaps (`N ___`) | Detect inline gap markers (number followed by blanks/dots); extract surrounding context |
| Completion (summary) | Prose paragraph with inline gaps | Join lines into paragraph; find gap markers; extract sentence context |
| Completion (sentence) | Numbered partial sentences ending with `___` | Match numbered lines; the prompt IS the incomplete sentence |
| Multiple Selection | Stem + options (A–E/F/G), choose 2+ | Same as MC but with more options and "choose TWO/THREE" in instruction |
| Matching | List of items + box of options (A–G) | Numbered items are questions; lettered box provides the option set |
| Heading Match | List of headings (i–x) + "paragraph" references | Roman-numeral headings are options; questions are "Paragraph A/B/C..." |
| Labeling | Diagram reference + numbered blanks | Numbered entries with short answers expected |

### 5.7 Answer Key Extraction

**Entry signal (corpus-driven):** Line containing "answer key" or "answers" (case-insensitive) that appears AFTER all test content.

**Structure (corpus-driven):** Cambridge answer keys are always organized:
1. By test (`Test 1`, `Test 2`, etc.)
2. Within each test, answers are listed 1–40 (Reading + Listening interleaved or separated by skill sub-headers like "Reading Passage 1")

**Line patterns:**
- `N answer` — number followed by space and answer text
- `N. answer` — number, dot, answer
- `N) answer` — number, paren, answer
- Multi-column: `N answer | M answer` (pipe or large whitespace as separator)

**Compound answers:** `19&20 B,D` or `19/20 B AND D` — both questions receive the listed answers.

### 5.8 Front-Matter / Appendix Detection

**Front-matter ends at:** First `Test 1` marker OR first skill-section content.

**Appendix starts at:** Content after the answer key region. Typically: sample writing answers, score band descriptors, acknowledgments.

**Heuristic:** If lines after the last answer-key entry contain "Band", "Score", "Sample", "Model answer", or "Acknowledgments" — classify as appendix and discard.

---

## 6. Heuristic Classification Summary

| Heuristic | Type | Rationale |
|-----------|------|-----------|
| 4 tests per book | Corpus-driven | Cambridge IELTS Academic specification |
| Skills in order L→R→W→S | Corpus-driven | Standard exam presentation order |
| 3 passages per reading test | Corpus-driven | Exam specification |
| 40 questions per reading/listening | Corpus-driven | Exam specification |
| "You should spend..." as passage anchor | Corpus-driven | Printed in every book as examinee instruction |
| `Questions X–Y` as block delimiter | Corpus-driven | Printed instruction format |
| Task instruction vocabulary | Corpus-driven | Standardized across all Cambridge IELTS books |
| Merged number splitting (e.g., 1428 → 14–28) | OCR-driven | Dash characters are frequently lost in OCR |
| Passage number clamping (74 → 4 → valid? → 1) | OCR-driven | OCR may merge adjacent digits |
| Footer stripping | OCR-driven | Page footers are OCR artifacts |
| SECTION/PART equivalence | Corpus-driven | Format evolved between editions but meaning is identical |
| Bullet normalization | OCR-driven | Different OCR engines render bullets differently |
| "Test N" false-positive filtering | OCR-driven | Prevents prose mentions from creating phantom tests |
| Skill-sequence reset as test boundary | Corpus-driven | Exploits the fixed L→R→W→S ordering |
| Score-band table detection | OCR-driven | Appendix content that should not be parsed |
| Multi-column answer key parsing | OCR-driven | OCR may linearize columns differently |

---

## 7. Design Principles

1. **Assume correct structure, handle noisy representation.** Every Cambridge IELTS book has 4 tests, each with L/R/W/S. The parser should never question this — only handle the fact that OCR may obscure the boundaries.

2. **Strongest anchor first.** When multiple signals could determine structure, prefer the highest-ranked anchor. Fall back to weaker signals only when stronger ones are absent.

3. **Context over pattern.** A regex match is only meaningful in the correct state. `Questions 14–20` in passage prose is noise; in a question-block zone after passage text, it's a structural delimiter. The state machine provides this context.

4. **Validate continuously.** Don't wait until the end to check for 40 questions. If the state machine exits a passage having found only 8 questions when 13 were expected, immediately flag it — this enables targeted recovery rather than silent data loss.

5. **No book-specific branches.** If you find yourself writing `if book == "IELTS16"`, you're fitting noise. Instead, write a generic recovery heuristic that handles the class of problem (e.g., "missing test boundary → infer from skill-sequence reset").

6. **Normalization is separate from parsing.** The normalization layer knows nothing about exam structure. The parser assumes normalized input. This separation means OCR improvements don't require parser changes, and parser improvements don't require re-OCR.

7. **Graceful degradation over silent failure.** When the parser cannot confidently extract a question, it should emit a placeholder with a confidence flag rather than silently dropping it. Downstream validation surfaces these gaps.

---

## 8. Expected Outcome

A parser built on this design should achieve:

| Metric | Target |
|--------|--------|
| Reading questions extracted | 40/40 for all tests where OCR text contains the questions |
| Listening questions extracted | 40/40 (requires strategy dispatch, not just `N.` matching) |
| Answer keys extracted | 40/40 (already working well) |
| False positive questions | 0 (state machine prevents passage-text misidentification) |
| Phantom tests | 0 (false-positive filtering on Test N markers) |
| New book support | Zero code changes needed for IELTS 18, 20, 21+ |
| Parser failures surfaced | All gaps reported with location and confidence level |
