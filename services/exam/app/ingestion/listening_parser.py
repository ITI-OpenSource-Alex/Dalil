from __future__ import annotations

import re
from typing import Any

from app.ingestion.parser import BaseParser, ParsedQuestion, ParsedTest


class ListeningParser(BaseParser):
    def parse_text(self, content: str | Any) -> dict[str, Any]:
        text = str(content)
        metadata = self._infer_metadata(text)
        answer_key = self._extract_answer_key(text)

        # Detect sections
        sections = []
        for m in re.finditer(r"SECTION\s*(\d+)|LISTENING\s*SECTION\s*(\d+)", text, re.IGNORECASE):
            sec = m.group(1) or m.group(2)
            if sec:
                sections.append(int(sec))

        # Extract questions
        questions: list[ParsedQuestion] = []
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for ln in lines:
            m_q = re.match(r"^(\d{1,2})\.\s*(.+)$", ln)
            if m_q:
                num = int(m_q.group(1))
                prompt = m_q.group(2).strip()
                # infer section from number ranges
                section_no = 1
                if num >= 1 and num <= 10:
                    section_no = 1
                elif num <= 20:
                    section_no = 2
                elif num <= 30:
                    section_no = 3
                else:
                    section_no = 4

                q = ParsedQuestion(
                    prompt=prompt,
                    question_type=self._classify_question_type(prompt),
                    number=num,
                    section_number=section_no,
                )
                questions.append(q)

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
            time_limit_seconds=30 * 60,
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

    def _extract_question_prompts(self, content: str) -> list[str]:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        return [line for line in lines if line.lower().startswith("question")]

    def _build_audio_s3_key(self, book_ref: str, test_number: int) -> str:
        return f"exam-audio/{book_ref}/{test_number}/section1.mp3"

    def _question_payload(self, question: ParsedQuestion) -> dict[str, Any]:
        return {
            "prompt": question.prompt,
            "question_type": question.question_type,
        }
