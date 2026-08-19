"""
app/ingestion/reading_parser.py
--------------------------------
Hierarchical, strategy-based Cambridge IELTS Academic Reading parser.

Architecture
============
  Book -> Test -> Reading section -> Passage 1/2/3 -> Question Block -> Questions

Each question block is classified from its instruction text and content shape,
then routed to a type-specific extractor.  No question numbers are ever
hardcoded; extraction always works from the dynamic block header "Questions X-Y".

Strategy dispatch
=================
  choose_two        – Multiple Choice, Choose TWO letters
  tfng              – True / False / Not Given
  ynng              – Yes / No / Not Given
  bullet_completion – Notes / Table completion with bullets
  summary_completion– Summary / paragraph inline gaps
  numbered_questions– Explicit numeric prefix per line

Answer key
==========
  _extract_answer_keys() already extracts 40/40 answers correctly.
  It is intentionally left unchanged.
"""

import re
from typing import Any

from app.ingestion.parser import BaseParser, ParsedQuestion, ParsedTest


# ---------------------------------------------------------------------------
# Module-level compiled patterns (shared across all strategy parsers)
# ---------------------------------------------------------------------------

# "Questions X-Y" or "Questions X and Y"
_BLOCK_RE = re.compile(
    r"(?i)\bQuestions?\s*(\d+)\s*(?:[-\u2013_to~]+|and)\s*(\d+)\b"
)

# "READING PASSAGE <N>" anchored to line start
_PASSAGE_HEADER_RE = re.compile(r"(?im)^\s*READING\s+PASSAGE\s+(\d+)\b")

# Passage preamble (header or time-budget instruction)
_PREAMBLE_RE = re.compile(
    r"(?i)(?:READING\s+PASSAGE\s+\d|You\s+should\s+spend)"
)

# Line whose first token is a question number:
#   "27 Hotel managers..."   "1. The writer..."   "3) According to..."
_NUM_PREFIX_RE = re.compile(r"^(\d{1,2})[.)]?\s+(.+)$")

# OCR bullet variants: *, •, ·, [, +, ~, *«, —, –, -  (at line start)
_BULLET_RE = re.compile(r"^[\*\u2022\u00b7\[\+~]|^\*[«\*]|^[\u2014\u2013]\s|^-\s")

# Strip leading bullet characters (including composite like *« or [ *)
_BULLET_STRIP_RE = re.compile(r"^[\*\u2022\u00b7\[\+~\-\u2014\u2013]+\s*(?:[«\*])?\s*")

# Inline gap markers used in summary/notes completion:
#   "23 ..."   "36....."   "37 ,"      "§" (OCR artefact for a blank)
#   "23 ……"    "23 ___"    "23 ____,"  (additional OCR variants)
_GAP_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*"
    r"(?:\.{2,}|\u2026+|_{2,},?|\u00a7|,\s|,(?!\d))"
)

# Boilerplate instruction lines — never part of question content
_INSTR_RE = re.compile(
    r"(?i)"
    r"write\s+your\s+answers?"
    r"|write\s+the\s+correct"
    r"|write\s+one\s+word"
    r"|choose\s+one\s+word\s+only"
    r"|in\s+boxes\s+\d+"
    r"|on\s+your\s+answer\s+sheet"
    r"|choose\s+(?:two|one|the\s+correct)\s+letters?"
    r"|nb\s+you\s+may"
    r"|complete\s+the\s+(?:summary|notes|table|sentences?|flow)"
    r"|do\s+the\s+following\s+statements?"
    r"|list\s+of\s+researchers?"
    r"|reading\s+passage\s+\d+"
    r"|you\s+should\s+spend"
    r"|which\s+paragraph"
    r"|look\s+at\s+the\s+following"
    r"|match\s+each\s+statement"
)

# TRUE/FALSE/NOT GIVEN / YES/NO label-definition lines (skip in TFNG blocks)
_TFNG_LABEL_RE = re.compile(
    r"(?i)^\s*(?:TRUE|FALSE|NOT\s+GIVEN|YES|NO)\s+(?:if\s+the|if\s+it)"
)

# Sentence-ending punctuation (for summary completion context extraction)
_SENT_END_RE = re.compile(r"[.!?](?:\s|$)")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class ReadingParser(BaseParser):
    """Strategy-based Cambridge IELTS Academic Reading parser."""

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    # GT section type mapping: passage index -> section type
    _GT_SECTION_TYPES = {
        1: "social",
        2: "work",
        3: "general_interest",
    }

    def parse_text(self, content: str | Any) -> dict[str, Any]:
        text = str(content)
        metadata = self._infer_metadata(text)
        test_number = metadata.get("test_number", 1)

        tests = self._split_into_tests(text)
        test_block = tests.get(test_number, "")
        if not test_block:
            test_block = text

        reading_section = self._isolate_reading_section(test_block)
        passage_blocks  = self._split_into_passages(reading_section)

        is_gt = metadata.get("exam_type") == "general"
        all_questions: list[ParsedQuestion] = []
        parsed_passages_text: list[str] = []

        for i, pb in enumerate(passage_blocks, 1):
            passage_text, questions_text = self._extract_passage_text_and_questions(pb)
            parsed_passages_text.append(passage_text.strip())
            all_questions.extend(self._extract_questions(questions_text, i))

        passage_text_combined = (
            "\n\n---\n\n".join(parsed_passages_text) if parsed_passages_text else None
        )
        answer_key = self._extract_answer_keys(text, test_number)

        test = ParsedTest(
            book_ref=metadata.get("book_ref", "IELTS-unknown"),
            test_number=test_number,
            exam_type=metadata.get("exam_type", "academic"),
            skill_area=metadata.get("skill_area", "reading"),
            passage_text=passage_text_combined,
            questions=all_questions,
            answer_key=answer_key,
            time_limit_seconds=3600,
        )

        question_payloads = [self._question_payload(q) for q in all_questions]

        if is_gt:
            for qp in question_payloads:
                pn = qp.get("passage_number")
                if pn and pn in self._GT_SECTION_TYPES:
                    qp["section_type"] = self._GT_SECTION_TYPES[pn]

        return {
            "book_ref": test.book_ref,
            "test_number": test.test_number,
            "exam_type": test.exam_type,
            "skill_area": test.skill_area,
            "passage_text": test.passage_text,
            "questions": question_payloads,
            "answer_key": test.answer_key,
            "time_limit_seconds": test.time_limit_seconds,
        }

    # -----------------------------------------------------------------------
    # Hierarchical section splitters
    # -----------------------------------------------------------------------

    def _split_into_tests(self, text: str) -> dict[int, str]:
        """Split the full OCR text into per-Test blocks."""
        matches = list(re.finditer(r"(?i)^Test\s+(\d+)\b", text, re.MULTILINE))
        tests: dict[int, str] = {}
        for i, m in enumerate(matches):
            t_num = int(m.group(1))
            start = m.end()
            end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            tests[t_num] = text[start:end]
        return tests

    def _isolate_reading_section(self, test_block: str) -> str:
        """Extract the READING section from a single-test block."""
        m = re.search(r"(?i)^READING\b", test_block, re.MULTILINE)
        if not m:
            return test_block
        start = m.end()
        end_m = re.search(
            r"(?i)^(LISTENING|WRITING|SPEAKING|TEST\s+\d+|Answer\s+keys?)\b",
            test_block[start:], re.MULTILINE,
        )
        return test_block[start: start + end_m.start()] if end_m else test_block[start:]

    def _split_into_passages(self, reading_section: str) -> list[str]:
        """Split the Reading section into passage blocks.

        Uses a single anchored regex to find all ``READING PASSAGE <N>``
        markers, deduplicates by passage number (keeps first occurrence),
        and slices between consecutive markers in document order.
        """
        markers = list(_PASSAGE_HEADER_RE.finditer(reading_section))
        if not markers:
            return [reading_section.strip()] if reading_section.strip() else []

        # Deduplicate by passage number — keep first occurrence only
        seen: dict[int, re.Match] = {}
        for m in markers:
            num = int(m.group(1))
            if num not in seen:
                seen[num] = m

        # Sort by document position and slice
        ordered = sorted(seen.values(), key=lambda m: m.start())
        blocks: list[str] = []

        # If there is text before the first marker, include it as a leading
        # passage block.  This covers the case where _isolate_reading_section
        # consumed the "READING" keyword from "READING PASSAGE 1", leaving
        # " PASSAGE 1\n<passage text>..." without a proper marker.
        first_start = ordered[0].start()
        if first_start > 0:
            leading = reading_section[:first_start].strip()
            if leading:
                blocks.append(leading)

        for i, m in enumerate(ordered):
            start = m.start()
            end = ordered[i + 1].start() if i + 1 < len(ordered) else len(reading_section)
            block = reading_section[start:end].strip()
            if block:
                blocks.append(block)
        return blocks

    def _extract_passage_text_and_questions(
        self, passage_block: str
    ) -> tuple[str, str]:
        """Split a passage block into (passage article text, questions section).

        Uses structural detection instead of a fixed character offset:
          1. Find the passage preamble (``READING PASSAGE N`` / ``You should
             spend ...``) to know where the header area ends.
          2. Walk through ``Questions X-Y`` headers.  Skip any that fall
             inside the preamble header area.
          3. Select the first header preceded by at least two substantive
             content lines (i.e. real passage prose exists before it).
          4. Fallback: if no header qualifies, use the last match.
        """
        matches = list(_BLOCK_RE.finditer(passage_block))
        if not matches:
            return passage_block, ""

        # Determine where the preamble header area ends
        header_end = 0
        preamble_m = _PREAMBLE_RE.search(passage_block)
        if preamble_m:
            nl = passage_block.find("\n", preamble_m.end())
            header_end = nl if nl != -1 else preamble_m.end()

        for m in matches:
            # Skip any Questions header that falls inside the preamble
            if m.start() < header_end:
                continue

            # Verify that real passage content exists before this header
            gap_text = passage_block[header_end:m.start()]
            substantive_lines = [
                ln for ln in gap_text.splitlines()
                if ln.strip() and not _INSTR_RE.search(ln) and len(ln.split()) > 2
            ]
            if len(substantive_lines) >= 1:
                return (
                    passage_block[:m.start()].strip(),
                    passage_block[m.start():].strip(),
                )

        # Fallback: use the last match (most likely the question section)
        last = matches[-1]
        return (
            passage_block[:last.start()].strip(),
            passage_block[last.start():].strip(),
        )

    # -----------------------------------------------------------------------
    # Question extraction — dispatcher
    # -----------------------------------------------------------------------

    def _extract_questions(
        self, questions_text: str, passage_number: int
    ) -> list[ParsedQuestion]:
        """
        Top-level dispatcher.  Finds every unique "Questions X-Y" block in the
        questions section, determines its type, and routes it to the correct
        strategy parser.  Never hardcodes question-number ranges.
        """
        if not questions_text:
            return []

        # Collect unique block headers, preserving document order
        seen: set[tuple[int, int]] = set()
        blocks: list[tuple[int, int, re.Match]] = []
        for m in _BLOCK_RE.finditer(questions_text):
            sq, eq = int(m.group(1)), int(m.group(2))
            if (sq, eq) not in seen:
                seen.add((sq, eq))
                blocks.append((sq, eq, m))

        questions: list[ParsedQuestion] = []

        for bidx, (start_q, end_q, m) in enumerate(blocks):
            block_start = m.end()
            block_end   = (
                blocks[bidx + 1][2].start() if bidx + 1 < len(blocks) else len(questions_text)
            )
            block_text = questions_text[block_start:block_end].strip()
            lines      = [ln.strip() for ln in block_text.splitlines() if ln.strip()]

            # First 5 lines give enough context for type detection
            instruction_sample = " ".join(lines[:5]).lower()
            q_type   = self._classify_question_type(instruction_sample)
            strategy = self._detect_strategy(instruction_sample, lines)

            if strategy == "choose_two":
                questions.extend(
                    self._parse_choose_two(lines, start_q, end_q, q_type, passage_number)
                )
            elif strategy == "tfng":
                questions.extend(
                    self._parse_tfng_or_ynng(lines, start_q, end_q, q_type, passage_number)
                )
            elif strategy == "ynng":
                questions.extend(
                    self._parse_tfng_or_ynng(lines, start_q, end_q, q_type, passage_number)
                )
            elif strategy == "bullet_completion":
                questions.extend(
                    self._parse_bullet_completion(lines, start_q, end_q, q_type, passage_number)
                )
            elif strategy == "summary_completion":
                questions.extend(
                    self._parse_summary_completion(lines, start_q, end_q, q_type, passage_number)
                )
            else:  # "numbered_questions" — safe default
                questions.extend(
                    self._parse_numbered_questions(lines, start_q, end_q, q_type, passage_number)
                )

        return questions

    # -----------------------------------------------------------------------
    # Strategy detection
    # -----------------------------------------------------------------------

    def _detect_strategy(self, instruction: str, lines: list[str]) -> str:
        """Determine the extraction strategy from instruction text and content shape.

        Priority layers (evaluated in order):
          1. Explicit instruction keywords  (most reliable).
          2. Content-shape inspection: bullet count vs numbered count, inline
             gaps, numeric prefixes.
          3. Prose-length heuristic for summary blocks where OCR dropped
             gap markers.
          4. Safe fallback to ``numbered_questions``.

        Never uses specific question number ranges.
        """
        low = instruction

        # ── Layer 1: keyword-based detection ────────────────────────────────
        if "choose two" in low or "which two" in low:
            return "choose_two"

        if (
            ("true" in low and "false" in low and "not given" in low)
            or "do the following statements agree" in low
        ):
            return "tfng"

        if "yes" in low and "no" in low and "not given" in low:
            return "ynng"

        if re.search(r"complete\s+the\s+(?:summary|notes|table|flow)", low):
            return "summary_completion"

        # ── Layer 2: content-shape inspection ───────────────────────────────
        content = [ln for ln in lines if not _INSTR_RE.search(ln)]

        bullet_count   = sum(1 for ln in content if _BULLET_RE.match(ln))
        gap_count      = sum(1 for ln in content if _GAP_RE.search(ln))
        numbered_count = sum(1 for ln in content if _NUM_PREFIX_RE.match(ln))

        # Bullets must outnumber numbered lines to avoid false detection on
        # blocks that happen to contain a stray bullet character.
        if bullet_count >= 2 and bullet_count > numbered_count:
            return "bullet_completion"

        if gap_count >= 1:
            return "summary_completion"

        if numbered_count >= 1:
            return "numbered_questions"

        # ── Layer 3: prose-length heuristic ─────────────────────────────────
        # Long prose lines with no other signals suggest a summary block
        # whose gap markers were lost by OCR.
        if content:
            avg_len = sum(len(ln) for ln in content) / len(content)
            if avg_len > 60:
                return "summary_completion"

        return "numbered_questions"  # safe fallback

    # -----------------------------------------------------------------------
    # Strategy parsers
    # -----------------------------------------------------------------------

    def _parse_numbered_questions(
        self,
        lines: list[str],
        start_q: int,
        end_q: int,
        q_type: str,
        passage_number: int,
    ) -> list[ParsedQuestion]:
        """Blocks where each question begins with its number.

        Rules
        -----
        - Lines matching ``^\\d+ text`` within [start_q, end_q] start a new question.
        - Non-numbered lines are appended to the preceding question.
        - Once a boilerplate instruction is encountered AFTER some questions have
          been extracted, continuation is suppressed (prevents researcher-name lists,
          section headers, etc. from polluting the last question's prompt).
        """
        questions: list[ParsedQuestion] = []
        stop_continuation = False

        for line in lines:
            if _INSTR_RE.search(line):
                if questions:
                    stop_continuation = True  # suppress noise after block ends
                continue

            m = _NUM_PREFIX_RE.match(line)
            if m:
                num = int(m.group(1))
                if start_q <= num <= end_q:
                    stop_continuation = False
                    questions.append(
                        ParsedQuestion(
                            prompt=m.group(2).strip(),
                            question_type=q_type,
                            number=num,
                            passage_number=passage_number,
                        )
                    )
            elif not stop_continuation and questions:
                questions[-1].prompt += " " + line

        return questions

    def _parse_tfng_or_ynng(
        self,
        lines: list[str],
        start_q: int,
        end_q: int,
        q_type: str,
        passage_number: int,
    ) -> list[ParsedQuestion]:
        """True/False/Not Given  and  Yes/No/Not Given.

        OCR behaviour in Cambridge IELTS scans
        ----------------------------------------
        - Instruction lines appear first (skipped by _INSTR_RE).
        - Label-definition lines (e.g. "TRUE if the statement agrees...") are skipped.
        - Some statements keep their number prefix (``9 Children with...``).
        - Others lose it; they are detected as new statements when they start with
          a capital letter and contain > 3 words.
        - Short continuation fragments (e.g. "with Lego.") are appended to the
          previous statement.
        - Once all questions up to end_q are assigned, uppercase-start lines are
          treated as section noise and dropped.
        """
        questions: list[ParsedQuestion] = []
        current_q = start_q

        for line in lines:
            if _INSTR_RE.search(line):
                continue
            if _TFNG_LABEL_RE.match(line):
                continue
            if len(line.split()) <= 1:
                continue  # single-char OCR noise

            # Prefer explicit numeric prefix
            m = _NUM_PREFIX_RE.match(line)
            if m:
                num = int(m.group(1))
                if start_q <= num <= end_q:
                    questions.append(
                        ParsedQuestion(
                            prompt=m.group(2).strip(),
                            question_type=q_type,
                            number=num,
                            passage_number=passage_number,
                        )
                    )
                    current_q = num + 1
                continue

            # All expected questions assigned → accept only lowercase continuations
            if current_q > end_q:
                if questions and not line[0].isupper():
                    questions[-1].prompt += " " + line
                continue  # drop uppercase noise lines

            # New statement: capital letter + substantive length
            if line[0].isupper() and len(line.split()) > 3:
                questions.append(
                    ParsedQuestion(
                        prompt=line,
                        question_type=q_type,
                        number=current_q,
                        passage_number=passage_number,
                    )
                )
                current_q += 1
            elif questions:
                # Continuation fragment (e.g. "with Lego.")
                questions[-1].prompt += " " + line

        return questions

    def _parse_bullet_completion(
        self,
        lines: list[str],
        start_q: int,
        end_q: int,
        q_type: str,
        passage_number: int,
    ) -> list[ParsedQuestion]:
        """Notes / Table completion where each answer slot is a bullet line.

        Algorithm
        ---------
        1. Merge continuation lines: non-bullet, non-instruction lines that
           follow a bullet are appended to that bullet's prompt.

        2. Classify each merged bullet as a **gap-bullet** (contains an inline
           question number from [start_q, end_q]) or a **plain-bullet**.

        3. Filter category headers: plain-bullets with ≤ 3 words that precede
           another bullet are likely structural headers, not question slots.

        4. Build the candidate list using gap-bullets as anchors:
           - Walk through gap-bullets in document order.
           - Fill gaps between anchors from plain-bullets in between.
           - Fill remaining slots after the last anchor from trailing
             plain-bullets.

        5. Assign sequential question numbers starting from start_q.

        All prompts come verbatim from OCR (after stripping the bullet character).
        """
        expected = end_q - start_q + 1

        # ── Step 1: merge continuation lines into preceding bullets ─────────
        merged: list[str] = []
        for line in lines:
            if _INSTR_RE.search(line):
                continue
            if _BULLET_RE.match(line):
                merged.append(line)
            elif merged and not _BULLET_RE.match(line):
                # Non-bullet line after a bullet → continuation
                merged[-1] += " " + line
            # else: non-bullet before any bullet → skip (preamble text)

        # ── Step 2: classify bullet lines ───────────────────────────────────
        gap_bullets:   list[tuple[int, int, str]] = []  # (idx, q_num, prompt)
        plain_bullets: list[tuple[int, str]]      = []  # (idx, prompt)

        for idx, line in enumerate(merged):
            prompt = _BULLET_STRIP_RE.sub("", line).strip()

            # Find which question number (if any) is embedded in this bullet
            detected_q: int | None = None
            for n in range(start_q, end_q + 1):
                if re.search(rf"(?<!\d){n}(?!\d)", prompt):
                    detected_q = n
                    break

            if detected_q is not None:
                gap_bullets.append((idx, detected_q, prompt))
            else:
                plain_bullets.append((idx, prompt))

        # Deduplicate gap-bullets by question number (keep first occurrence)
        seen_q: set[int] = set()
        unique_gap: list[tuple[int, int, str]] = []
        for li, q_num, p in gap_bullets:
            if q_num not in seen_q:
                seen_q.add(q_num)
                unique_gap.append((li, q_num, p))
        gap_bullets = unique_gap

        # ── Step 3: filter category headers from plain_bullets ──────────────
        # A plain bullet with ≤ 3 words followed by another bullet is likely
        # a category header (e.g. "Advantages:", "Early history"), not a
        # question slot.
        filtered_plain: list[tuple[int, str]] = []
        for i, (idx, prompt) in enumerate(plain_bullets):
            word_count = len(prompt.split())
            if word_count <= 3:
                # Check if followed by another bullet (gap or plain)
                next_idxs = (
                    [gi for gi, _, _ in gap_bullets if gi > idx]
                    + [pi for pi, _ in plain_bullets if pi > idx]
                )
                if next_idxs:
                    continue  # skip — likely a category header
            filtered_plain.append((idx, prompt))
        plain_bullets = filtered_plain

        # ── Step 4: build ordered candidate list using anchors ──────────────
        candidates: list[str] = []
        prev_q   = start_q - 1
        prev_li  = -1

        for li, q_num, prompt in gap_bullets:
            # Fill gap between previous anchor and this one
            gap_size = q_num - prev_q - 1
            if gap_size > 0:
                fillers = [p for fli, p in plain_bullets if prev_li < fli < li]
                candidates.extend(fillers[:gap_size])

            candidates.append(prompt)
            prev_q  = q_num
            prev_li = li

        # Fill remaining questions after the last anchor
        remaining = end_q - prev_q
        if remaining > 0:
            tail = [p for fli, p in plain_bullets if fli > prev_li]
            candidates.extend(tail[:remaining])

        # Fallback: if candidate list is still short, take any unused plain bullets
        if len(candidates) < expected:
            used_set = set(candidates)
            extra = [p for _, p in plain_bullets if p not in used_set]
            candidates.extend(extra[: expected - len(candidates)])

        # Trim to expected count
        candidates = candidates[:expected]

        return [
            ParsedQuestion(
                prompt=prompt,
                question_type=q_type,
                number=start_q + seq,
                passage_number=passage_number,
            )
            for seq, prompt in enumerate(candidates)
        ]

    def _parse_summary_completion(
        self,
        lines: list[str],
        start_q: int,
        end_q: int,
        q_type: str,
        passage_number: int,
    ) -> list[ParsedQuestion]:
        """Summary / Notes paragraph completion with **inline** gap markers.

        Strategy
        --------
        1. Skip boilerplate instruction lines; join the rest into a paragraph.
        2. For each question number N in [start_q, end_q]:
           a. Search for the inline gap marker  ``N ...`` / ``N,`` / etc.
           b. If found, try to extract the **complete sentence** containing
              the gap (using sentence-boundary detection).
           c. If the sentence is too long (> 500 chars) or boundaries cannot
              be determined, fall back to ±120 chars of surrounding context.
           d. If the gap marker is not found, search for ``\\bN\\b`` as fallback.
           e. If still not found, use the whole paragraph (no fabrication).
        3. All prompt text is taken verbatim from OCR.
        """
        content = [
            ln for ln in lines
            if not _INSTR_RE.search(ln) and len(ln.split()) > 1
        ]
        paragraph = " ".join(content)

        questions: list[ParsedQuestion] = []
        for q_num in range(start_q, end_q + 1):
            # Primary: gap marker (dots, ellipsis, underscores, comma, §)
            gap_pat = re.compile(
                rf"(?<!\d){q_num}\s*(?:\.{{2,}}|\u2026+|_{{2,}},?|\u00a7|,\s|,(?!\d))"
            )
            m = gap_pat.search(paragraph)

            if not m:
                # Fallback: bare number in sentence context (no adjacent digits)
                bare_pat = re.compile(rf"(?<!\d){q_num}(?!\d)")
                m = bare_pat.search(paragraph)

            if m:
                prompt = self._extract_sentence_context(paragraph, m.start(), m.end())
            else:
                prompt = paragraph  # whole paragraph as fallback

            questions.append(
                ParsedQuestion(
                    prompt=prompt,
                    question_type=q_type,
                    number=q_num,
                    passage_number=passage_number,
                )
            )

        return questions

    @staticmethod
    def _extract_sentence_context(
        paragraph: str, match_start: int, match_end: int
    ) -> str:
        """Extract the sentence containing a gap match.

        Tries to find sentence boundaries (`.`/`!`/`?` followed by whitespace)
        around the match.  Falls back to ±120 characters if the detected
        sentence is too long (> 500 chars) or no boundaries are found.
        """
        # Find sentence start: look backwards for sentence-ending punctuation
        sent_start = 0
        search_region = paragraph[:match_start]
        # rfind the last '. ' or '! ' or '? ' before the match
        for i in range(len(search_region) - 1, -1, -1):
            if search_region[i] in ".!?" and i + 1 < len(search_region) and search_region[i + 1] in " \t\n":
                sent_start = i + 2  # skip the punctuation and space
                break

        # Find sentence end: look forwards for sentence-ending punctuation
        sent_end = len(paragraph)
        end_match = _SENT_END_RE.search(paragraph[match_end:])
        if end_match:
            sent_end = match_end + end_match.end()

        # If the detected sentence is reasonable length, use it
        if sent_end - sent_start <= 500:
            result = paragraph[sent_start:sent_end].strip()
            if result:
                return result

        # Fallback: fixed ±120 character window
        ctx_s = max(0, match_start - 120)
        ctx_e = min(len(paragraph), match_end + 120)
        return paragraph[ctx_s:ctx_e].strip()

    def _parse_choose_two(
        self,
        lines: list[str],
        start_q: int,
        end_q: int,
        q_type: str,
        passage_number: int,
    ) -> list[ParsedQuestion]:
        """
        Multiple Choice — Choose TWO letters (e.g. "Questions 19 and 20").

        Both questions in the block receive the **same** prompt (stem + options).
        The answer key stores the two correct letters as separate entries.
        Keeping the full text for both questions allows either question to be
        presented independently to the test-taker.
        """
        content = [ln for ln in lines if not _INSTR_RE.search(ln)]
        prompt  = " ".join(content).strip() or " ".join(lines).strip()

        return [
            ParsedQuestion(
                prompt=prompt,
                question_type=q_type,
                number=q_num,
                passage_number=passage_number,
            )
            for q_num in range(start_q, end_q + 1)
        ]

    # -----------------------------------------------------------------------
    # Answer key extraction  (unchanged — already returns 40/40 correctly)
    # -----------------------------------------------------------------------

    def _extract_answer_keys(self, text: str, test_number: int) -> dict[str, str]:
        match_ak = re.search(r"(?i)\bAnswer\s*keys?", text)
        if not match_ak:
            return {}

        ak_text = text[match_ak.end():]

        rp1_matches = list(re.finditer(r"(?i)Reading\s*Passage\s*1", ak_text))
        if not rp1_matches:
            ak_test_block = ak_text
        else:
            if test_number <= len(rp1_matches):
                start = rp1_matches[test_number - 1].start()
                end   = (
                    rp1_matches[test_number].start()
                    if test_number < len(rp1_matches)
                    else len(ak_text)
                )
                ak_test_block = ak_text[start:end]
            else:
                ak_test_block = ak_text

        answers: dict[str, str] = {}
        for line in ak_test_block.splitlines():
            line = line.strip()
            for m in re.finditer(
                r"\b(\d{1,2})[A-Za-z]?(?:&(\d{1,2})[A-Za-z]?)?\s+([A-Za-z]+[^\d\n]*)",
                line,
            ):
                q1, q2, ans = m.group(1), m.group(2), m.group(3).strip()
                ans = re.sub(
                    r"(?i)(IN EITHER ORDER|Reading Passage.*|Questions.*)", "", ans
                ).strip()
                if ans:
                    if 1 <= int(q1) <= 40:
                        answers[q1] = ans
                    if q2 and 1 <= int(q2) <= 40:
                        answers[q2] = ans

        return answers
