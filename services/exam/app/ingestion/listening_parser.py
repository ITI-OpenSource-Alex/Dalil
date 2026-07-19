import re
from typing import Any
from app.ingestion.parser import BaseParser, ParsedQuestion, ParsedTest


class ListeningParser(BaseParser):
    def parse_text(self, content: str) -> dict[str, Any]:
        text = self._normalize_text(content)
        metadata = self._infer_metadata(text, source=None)
        answer_key = self._extract_answer_key(text)

        all_questions: list[ParsedQuestion] = []

        # 1. Match all "Questions X-Y" and merged ones like "Questions 1310"
        from app.ingestion.parser_helpers import parse_question_range, QUESTION_BLOCK_RE


        blocks = []
        seen = set()
        for m in QUESTION_BLOCK_RE.finditer(text):
            raw_match = m.group(1).replace(" ", "")
            # If it has a standard separator, split it
            if (
                "-" in raw_match
                or "to" in raw_match.lower()
                or "and" in raw_match.lower()
                or "–" in raw_match
            ):
                # Basic split for standard cases
                parts = re.split(r"-|to|and|–", raw_match, flags=re.IGNORECASE)
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    sq, eq = int(parts[0]), int(parts[1])
                    if (sq, eq) not in seen:
                        seen.add((sq, eq))
                        blocks.append((sq, eq, m))
            else:
                # Merged block or OCR noise like '1310'
                parsed_range = parse_question_range(raw_match)
                if parsed_range:
                    # Pick the first valid candidate (since listening parser doesn't use expected_number yet)
                    valid_candidates = [
                        (s, e) for s, e in parsed_range.candidates if e - s <= 15
                    ]
                    if valid_candidates:
                        sq, eq = valid_candidates[0]
                        if (sq, eq) not in seen:
                            seen.add((sq, eq))
                            blocks.append((sq, eq, m))

        blocks.sort(key=lambda b: b[2].start())

        # 2. Extract questions for each block
        for bidx, (start_q, end_q, m) in enumerate(blocks):
            if not (1 <= start_q <= 40 and 1 <= end_q <= 40 and start_q <= end_q):
                continue

            block_start = m.end()
            block_end = (
                blocks[bidx + 1][2].start() if bidx + 1 < len(blocks) else len(text)
            )
            block_text = text[block_start:block_end]

            expected = end_q - start_q + 1
            lines = [l.strip() for l in block_text.splitlines() if l.strip()]

            # Is it multiple choice? Check for A, B, C options
            mc_questions = []
            current_q = []
            for line in lines:
                if re.match(r"^[A-C]\s", line):
                    continue
                if len(line.split()) > 3:
                    current_q.append(line)
                elif current_q and line.endswith("?"):
                    current_q.append(line)

            if current_q:
                mc_questions.append(" ".join(current_q))

            # If we collected exactly 'expected' lines that look like questions, map them directly
            if len(mc_questions) == expected:
                for seq, prompt in enumerate(mc_questions):
                    all_questions.append(
                        ParsedQuestion(
                            prompt=prompt,
                            question_type="Multiple Choice",
                            number=start_q + seq,
                            section_number=(start_q - 1) // 10 + 1,
                        )
                    )
            elif (
                len(mc_questions) == 1
                and expected > 1
                and (
                    "TWO" in mc_questions[0].upper()
                    or "THREE" in mc_questions[0].upper()
                    or "TWO" in block_text.upper()
                    or "THREE" in block_text.upper()
                )
            ):
                for seq in range(expected):
                    all_questions.append(
                        ParsedQuestion(
                            prompt=mc_questions[0],
                            question_type="Multiple Choice",
                            number=start_q + seq,
                            section_number=(start_q - 1) // 10 + 1,
                        )
                    )
            else:
                # Try finding numbers in the text
                gap_questions = {}
                for num in range(start_q, end_q + 1):
                    # Find a line with this number as a distinct token
                    found_line = ""
                    for line in lines:
                        if re.search(rf"(?<!\d){num}(?!\d)", line):
                            found_line = line
                            break
                    if found_line:
                        gap_questions[num] = found_line

                # If we missed some numbers, it might be an unnumbered matching list at the end
                if len(gap_questions) < expected:
                    valid_lines = [
                        l for l in lines if l and not l.upper().startswith("QUESTIONS")
                    ]
                    if len(valid_lines) >= expected:
                        tail = valid_lines[-expected:]
                        # If the tail items look like short matching items (no numbers), use them
                        if all(
                            len(t.split()) < 15 and not re.search(r"\b\d{2,}\b", t)
                            for t in tail
                        ):
                            gap_questions = {start_q + i: t for i, t in enumerate(tail)}

                for num, prompt in gap_questions.items():
                    all_questions.append(
                        ParsedQuestion(
                            prompt=prompt,
                            question_type="Completion"
                            if "Choose" not in block_text
                            else "Multiple Choice",
                            number=num,
                            section_number=(start_q - 1) // 10 + 1,
                        )
                    )

        # Sort and deduplicate by number just in case
        unique_qs = {}
        for q in all_questions:
            if q.number not in unique_qs:
                unique_qs[q.number] = q

        final_questions = [unique_qs[n] for n in sorted(unique_qs.keys())]

        test = ParsedTest(
            book_ref=metadata.get("book_ref", "IELTS-unknown"),
            test_number=metadata.get("test_number", 1),
            exam_type=metadata.get("exam_type", "academic"),
            skill_area="listening",
            questions=final_questions,
            answer_key=answer_key,
            audio_s3_key=self._build_audio_s3_key(
                metadata.get("book_ref", "IELTS-unknown"),
                metadata.get("test_number", 1),
            ),
            time_limit_seconds=30 * 60,
        )

        return {
            "book_ref": test.book_ref,
            "test_number": test.test_number,
            "exam_type": test.exam_type,
            "skill_area": test.skill_area,
            "passage_text": None,
            "questions": [
                self._question_payload(question) for question in final_questions
            ],
            "answer_key": test.answer_key,
            "audio_s3_key": test.audio_s3_key,
            "time_limit_seconds": test.time_limit_seconds,
        }

    def _build_audio_s3_key(self, book_ref: str, test_number: int) -> str:
        return f"exam-audio/{book_ref}/{test_number}/section1.mp3"

    def _question_payload(self, question: ParsedQuestion) -> dict[str, Any]:
        return {
            "number": question.number,
            "prompt": question.prompt,
            "question_type": question.question_type,
            "instructions": question.instructions,
            "passage_number": question.passage_number,
            "section_number": question.section_number,
        }
