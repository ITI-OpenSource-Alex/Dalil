from __future__ import annotations

import re
from typing import Any

from app.ingestion.parser import BaseParser, ParsedQuestion, ParsedTest


_QUESTION_RANGE_RE = re.compile(
    r"(?i)\bQuestions?\s*(\d{1,2})\s*(?:[-\u2013\u2014~]|to|and)\s*(\d{1,2})\b"
)
_EXPLICIT_QUESTION_RE = re.compile(r"^(\d{1,2})[.)]?\s+(.+)$")
_INSTRUCTION_RE = re.compile(
    r"(?i)^(?:choose|complete|label|write|which|what|match|select|answer)\b"
)
_BOILERPLATE_RE = re.compile(
    r"(?i)^(?:listening test audio|p[.]?\s*\d+|\d+\s+p[.]?\s*\d+|"
    r"www\.|ielts\s*pop|izone\.edu|test\s+\d+\s*$)"
)


class ListeningParser(BaseParser):
    """Parse Cambridge Listening layouts into forty numbered questions.

    Cambridge books commonly express questions as completion gaps inside a
    table or as a shared matching/map block.  Individual questions therefore
    do not consistently begin with ``1.``.  The parser uses the printed
    ``Questions X-Y`` ranges as the source of truth and extracts the most
    specific source context available for each number.
    """

    def parse_text(self, content: str | Any) -> dict[str, Any]:
        text = self._normalize_listening_text(str(content))
        metadata = self._infer_metadata(text)
        listening_section = self._isolate_listening_section(text)
        questions = self._extract_questions(listening_section)
        answer_key = self._extract_answer_key(text)

        test = ParsedTest(
            book_ref=metadata.get("book_ref", "IELTS-unknown"),
            test_number=metadata.get("test_number", 1),
            exam_type=metadata.get("exam_type", "academic"),
            skill_area="listening",
            questions=questions,
            answer_key=answer_key,
            audio_s3_key=self._build_audio_s3_key(
                metadata.get("book_ref", "IELTS-unknown"),
                metadata.get("test_number", 1),
            ),
            time_limit_seconds=40 * 60,
        )

        return {
            "book_ref": test.book_ref,
            "test_number": test.test_number,
            "exam_type": test.exam_type,
            "skill_area": test.skill_area,
            "passage_text": None,
            "questions": [self._question_payload(question) for question in questions],
            "answer_key": test.answer_key,
            "audio_s3_key": test.audio_s3_key,
            "time_limit_seconds": test.time_limit_seconds,
        }

    @staticmethod
    def _normalize_listening_text(text: str) -> str:
        # OCR sometimes reads an en dash as the digit 3: 1-10 becomes 1310,
        # 11-20 becomes 11320, and so on.
        text = re.sub(
            r"(?i)(Questions?\s+)(1|11|21|31)3(10|20|30|40)\b",
            lambda match: f"{match.group(1)}{match.group(2)}-{match.group(3)}",
            text,
        )
        return text.replace("\u2212", "-")

    @staticmethod
    def _isolate_listening_section(text: str) -> str:
        end_match = re.search(
            r"(?im)^\s*(?:ACADEMIC\s+)?READING(?:\s+PASSAGE|\s*$)",
            text,
        )
        end_candidates = [end_match.start()] if end_match else []

        # Some scanned books lose the READING header.  The Listening pages
        # still end after the first non-header occurrence of question 40 and
        # its page-reference footer, before the Reading passage begins.
        for number_match in re.finditer(r"(?<!\d)40(?!\d)", text):
            line_start = text.rfind("\n", 0, number_match.start()) + 1
            line_end = text.find("\n", number_match.end())
            line_end = len(text) if line_end == -1 else line_end
            line = text[line_start:line_end]
            if re.search(r"(?i)Questions?\s*31\s*[-\u2013\u2014~]\s*40", line):
                continue
            footer = re.search(
                r"(?im)^.*(?:p\.\s*[A-Za-z]*\d+|\bp\s+\d+|www\.[^\s]+).*$",
                text[line_end:],
            )
            if footer:
                end_candidates.append(line_end + footer.end())
            else:
                end_candidates.append(line_end)
            break

        end = min(end_candidates) if end_candidates else len(text)
        start_match = re.search(r"(?im)^\s*LISTENING\s*$", text[:end])
        start = start_match.end() if start_match else 0
        return text[start:end]

    def _extract_questions(self, section: str) -> list[ParsedQuestion]:
        section = self._add_implicit_part_ranges(section)
        section = self._recover_unnumbered_choose_two(section)
        section = self._recover_missing_part_four(section)
        if not any(
            int(match.group(1)) <= 1 <= int(match.group(2))
            for match in _QUESTION_RANGE_RE.finditer(section)
        ):
            section = f"Questions 1-10\n{section}"
        markers = list(_QUESTION_RANGE_RE.finditer(section))
        blocks: list[tuple[int, int, str]] = []

        for index, marker in enumerate(markers):
            start_q, end_q = int(marker.group(1)), int(marker.group(2))
            if not (1 <= start_q <= end_q <= 40):
                continue
            block_end = (
                markers[index + 1].start() if index + 1 < len(markers) else len(section)
            )
            leading = self._leading_instructions(section, marker.start())
            block = self._clean_block(f"{leading}\n{section[marker.end() : block_end]}")
            blocks.append((start_q, end_q, block))

        questions: list[ParsedQuestion] = []
        for number in range(1, 41):
            candidates = [block for block in blocks if block[0] <= number <= block[1]]
            if not candidates:
                continue

            # Prefer the narrowest printed range.  When OCR duplicates a range,
            # use the copy containing the most source context.
            start_q, end_q, block = min(
                candidates,
                key=lambda item: (
                    not bool(item[2].strip()),
                    item[1] - item[0],
                    -len(item[2]),
                ),
            )
            prompt = self._extract_prompt(block, number, start_q, end_q)
            instructions = self._extract_instructions(block)
            classification_source = f"{instructions or ''} {block[:400]}"
            questions.append(
                ParsedQuestion(
                    prompt=prompt,
                    question_type=self._classify_listening_type(classification_source),
                    number=number,
                    instructions=instructions,
                    section_number=((number - 1) // 10) + 1,
                )
            )

        return questions

    @staticmethod
    def _recover_unnumbered_choose_two(section: str) -> str:
        markers = list(_QUESTION_RANGE_RE.finditer(section))
        restart_at = len(section)
        reached_part_three = False
        for marker in markers:
            start_q, end_q = int(marker.group(1)), int(marker.group(2))
            if start_q >= 21 and end_q >= 30:
                reached_part_three = True
            elif reached_part_three and start_q <= 10:
                restart_at = marker.start()
                break
        listening_markers = [
            marker for marker in markers if marker.start() < restart_at
        ]
        covered = {
            number
            for marker in listening_markers
            for number in range(int(marker.group(1)), int(marker.group(2)) + 1)
        }
        if {17, 18, 19, 20}.issubset(covered):
            return section

        part_three_at = next(
            (
                marker.start()
                for marker in listening_markers
                if int(marker.group(1)) >= 21 and int(marker.group(2)) >= 30
            ),
            len(section),
        )
        choose_two = list(
            re.finditer(
                r"(?im)^\s*Choose\s+TWO\s+(?:letters?|answers?)\b",
                section[:part_three_at],
            )
        )
        if len(choose_two) >= 2:
            additions = [
                (choose_two[-2].start(), "Questions 17 and 18\n"),
                (choose_two[-1].start(), "Questions 19 and 20\n"),
            ]
        else:
            stems = list(
                re.finditer(
                    r"(?im)^\s*What\s+does\s+the\s+speaker\s+say\s+about\b",
                    section[:part_three_at],
                )
            )
            if len(choose_two) != 1 or len(stems) < 2:
                return section
            additions = [
                (choose_two[0].start(), "Questions 17 and 18\n"),
                (stems[-1].start(), "Questions 19 and 20\n"),
            ]
        for position, header in reversed(additions):
            section = f"{section[:position]}{header}{section[position:]}"
        return section

    @staticmethod
    def _recover_missing_part_four(section: str) -> str:
        markers = list(_QUESTION_RANGE_RE.finditer(section))
        restart_at = len(section)
        reached_part_three = False
        for marker in markers:
            start_q, end_q = int(marker.group(1)), int(marker.group(2))
            if end_q >= 30:
                reached_part_three = True
            elif reached_part_three and start_q <= 10:
                restart_at = marker.start()
                break

        listening_markers = [
            marker for marker in markers if marker.start() < restart_at
        ]
        part_four = next(
            (
                marker
                for marker in listening_markers
                if int(marker.group(1)) <= 31 <= int(marker.group(2))
            ),
            None,
        )

        if part_four is None:
            part_three = next(
                (
                    marker
                    for marker in reversed(listening_markers)
                    if int(marker.group(2)) == 30
                ),
                None,
            )
            if part_three is None:
                return section

            footer = re.search(
                r"(?im)^.*(?:p\.\s*[A-Za-z]*\d+|\bp\s+\d+|www\.[^\s]+).*$",
                section[part_three.end() : restart_at],
            )
            if footer is None:
                return section
            insert_at = part_three.end() + footer.end()
            section = f"{section[:insert_at]}\nQuestions 31-40\n{section[insert_at:]}"
            restart_at += len("\nQuestions 31-40\n")
            part_four = next(
                marker
                for marker in _QUESTION_RANGE_RE.finditer(section)
                if marker.start() >= insert_at
                and int(marker.group(1)) <= 31 <= int(marker.group(2))
            )

        # The first page-reference footer after Part 4 is the Listening/Reading
        # boundary even when OCR dropped the printed READING heading.
        footer = re.search(
            r"(?im)^.*(?:p\.\s*[A-Za-z]*\d+|\bp\s+\d+|www\.[^\s]+).*$",
            section[part_four.end() : restart_at],
        )
        if footer is None:
            return section[:restart_at]
        return section[: part_four.end() + footer.end()]

    @staticmethod
    def _add_implicit_part_ranges(section: str) -> str:
        ranges = {1: (1, 10), 2: (11, 20), 3: (21, 30), 4: (31, 40)}

        def replace(match: re.Match[str]) -> str:
            line = match.group(0)
            if re.search(r"(?i)Questions?", line):
                return line
            part = int(match.group(1))
            start_q, end_q = ranges[part]
            return f"{line} Questions {start_q}-{end_q}"

        return re.sub(
            r"(?im)^\s*(?:LISTENING\s+)?(?:PART|SECTION)\s*([1-4])[^\n]*$",
            replace,
            section,
        )

    @staticmethod
    def _clean_block(block: str) -> str:
        lines: list[str] = []
        for raw_line in block.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line or _BOILERPLATE_RE.match(line):
                continue
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _leading_instructions(section: str, marker_start: int) -> str:
        line_start = section.rfind("\n", 0, marker_start) + 1
        previous_lines = section[:line_start].splitlines()[-3:]
        same_line_prefix = section[line_start:marker_start].strip()
        candidates = [*previous_lines, same_line_prefix]
        return "\n".join(
            line.strip()
            for line in candidates
            if line.strip() and _INSTRUCTION_RE.match(line.strip())
        )

    def _extract_prompt(self, block: str, number: int, start_q: int, end_q: int) -> str:
        lines = block.splitlines()
        for index, line in enumerate(lines):
            match = _EXPLICIT_QUESTION_RE.match(line)
            if not match or int(match.group(1)) != number:
                continue

            prompt_lines = [match.group(2).strip()]
            for continuation in lines[index + 1 :]:
                next_match = _EXPLICIT_QUESTION_RE.match(continuation)
                if next_match and start_q <= int(next_match.group(1)) <= end_q:
                    break
                if _INSTRUCTION_RE.match(continuation):
                    break
                prompt_lines.append(continuation)
            return self._truncate_prompt(" ".join(prompt_lines))

        # Completion and table layouts place the number inside a sentence or
        # bullet rather than at its start.  Preserve nearby verbatim context.
        number_pattern = re.compile(rf"(?<!\d){number}(?!\d)")
        for index, line in enumerate(lines):
            if not number_pattern.search(line):
                continue
            if re.search(
                r"(?i)(?:p[.]?\s*[A-Za-z]*\d+|www\.|\bPART\s+[1-4])",
                line,
            ):
                continue
            context = " ".join(lines[max(0, index - 1) : min(len(lines), index + 2)])
            return self._truncate_prompt(context)

        # Matching blocks share one stem/options list across several question
        # numbers.  Returning that source block for each number is intentional.
        return self._truncate_prompt(block)

    @staticmethod
    def _truncate_prompt(prompt: str, limit: int = 1600) -> str:
        normalized = re.sub(r"\s+", " ", prompt).strip()
        return normalized[:limit].rstrip()

    @staticmethod
    def _extract_instructions(block: str) -> str | None:
        instructions = [
            line for line in block.splitlines()[:8] if _INSTRUCTION_RE.match(line)
        ]
        return " ".join(instructions) or None

    def _classify_listening_type(self, source: str) -> str:
        lowered = source.lower()
        if (
            "label the map" in lowered
            or "label the plan" in lowered
            or "label the diagram" in lowered
        ):
            return "Diagram Labelling"
        if "complete the table" in lowered:
            return "Table Completion"
        if "complete the notes" in lowered:
            return "Notes Completion"
        if "complete the form" in lowered:
            return "Form Completion"
        if "complete the flow" in lowered:
            return "Flow Chart Completion"
        if "complete the sentence" in lowered:
            return "Sentence Completion"
        if "choose" in lowered or "correct letter" in lowered:
            return "Multiple Choice"
        return self._classify_question_type(source)

    def _extract_question_prompts(self, content: str) -> list[str]:
        return [question.prompt for question in self._extract_questions(content)]

    @staticmethod
    def _build_audio_s3_key(book_ref: str, test_number: int) -> str:
        return f"exam-audio/{book_ref}/{test_number}/section1.mp3"
