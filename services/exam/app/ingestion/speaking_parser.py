"""
app/ingestion/speaking_parser.py
--------------------------------
Cambridge IELTS Speaking test parser.

Extracts Part 1 topics/questions, Part 2 cue cards (with bullet points),
and Part 3 discussion questions. Each test produces one record with
skill_area='speaking', questions JSONB containing parts 1-3, and
time_limit_seconds=900 (approximate total speaking time).
"""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.parser import BaseParser


class SpeakingParser(BaseParser):
    """Extracts IELTS Speaking Part 1, 2, and 3 content."""

    def parse_text(self, content: str | Any) -> dict[str, Any]:
        text = str(content)
        metadata = self._infer_metadata(text)
        metadata["skill_area"] = "speaking"

        # Isolate the speaking section first to avoid matching Listening or Reading parts
        # Since Speaking is always at the end of the test block, we can safely restrict our search
        # to the last 3000 characters.
        search_text = text[-3000:] if len(text) > 3000 else text

        m_examiner = re.search(
            r"(?i)The\s+examiner\s+asks\s+the\s+candidate", search_text
        )
        m_part2 = re.search(
            r"(?i)(PART\s+2\b|Describe\s+a\b|Talk\s+about\b)", search_text
        )

        if m_examiner:
            search_text = search_text[m_examiner.start() :]
        elif m_part2:
            # Go back ~1000 chars from Part 2 to capture Part 1
            start_idx = max(0, m_part2.start() - 1000)
            search_text = search_text[start_idx:]

        part1 = self._extract_part1(search_text)
        part2 = self._extract_part2(search_text)
        part3 = self._extract_part3(search_text)

        questions: list[dict[str, Any]] = []
        q_number = 1

        for topic in part1:
            questions.append(
                {
                    "number": q_number,
                    "prompt": topic,
                    "question_type": "Speaking Part 1",
                    "instructions": "Answer the question in 1-2 sentences.",
                    "passage_number": None,
                    "section_number": 1,
                }
            )
            q_number += 1

        if part2:
            questions.append(
                {
                    "number": q_number,
                    "prompt": part2["topic"],
                    "question_type": "Speaking Part 2",
                    "instructions": "Speak for 1-2 minutes on this topic.",
                    "passage_number": None,
                    "section_number": 2,
                    "bullet_points": part2.get("bullets", []),
                }
            )
            q_number += 1

        for discussion_q in part3:
            questions.append(
                {
                    "number": q_number,
                    "prompt": discussion_q,
                    "question_type": "Speaking Part 3",
                    "instructions": "Discuss this question in detail.",
                    "passage_number": None,
                    "section_number": 3,
                }
            )
            q_number += 1

        return {
            "book_ref": metadata.get("book_ref", "IELTS-unknown"),
            "test_number": metadata.get("test_number", 1),
            "exam_type": metadata.get("exam_type", "academic"),
            "skill_area": "speaking",
            "passage_text": None,
            "questions": questions,
            "answer_key": {},
            "time_limit_seconds": 900,
        }

    def _extract_part1(self, search_text: str) -> list[str]:
        m = re.search(r"(?i)(PART\s+2\b|Describe\s+a\b|Talk\s+about\b)", search_text)
        block = search_text[: m.start()] if m else search_text

        questions = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(
                r"(?i)^(the examiner|introduction|let|example|part 1|speaking)",
                stripped,
            ):
                continue
            if "?" in stripped or re.match(r"^\d+[.)]\s+", stripped):
                cleaned = re.sub(r"^\d+[.)]\s+", "", stripped)
                if cleaned:
                    questions.append(cleaned)
        return questions

    def _extract_part2(self, search_text: str) -> dict[str, Any] | None:
        m = re.search(r"(?i)(PART\s+2\b|Describe\s+a\b|Talk\s+about\b)", search_text)
        if not m:
            return None

        block = search_text[m.start() :]
        m3 = re.search(r"(?i)(PART\s+3\b)", block)
        if m3:
            block = block[: m3.start()]
        else:
            lines = block.splitlines()
            end_idx = len(lines)
            for i, line in enumerate(lines):
                if i > 0 and "?" in line:
                    end_idx = i
                    if (
                        i > 1
                        and len(lines[i - 1].split()) <= 4
                        and not lines[i - 1].endswith(".")
                    ):
                        end_idx = i - 1
                    break
            block = "\n".join(lines[:end_idx])

        prompt = ""
        bullets = []
        in_bullets = False
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"(?i)^(part 2)", stripped):
                continue

            if (
                re.match(r"(?i)^(you should say|and explain)", stripped)
                or stripped.startswith("e ")
                or stripped.startswith("o ")
                or stripped.startswith("- ")
                or stripped.startswith("what ")
                or stripped.startswith("how ")
                or stripped.startswith("who ")
                or stripped.startswith("where ")
                or stripped.startswith("when ")
                or stripped.startswith("why ")
            ):
                in_bullets = True
                bullets.append(stripped)
            elif not in_bullets:
                prompt += stripped + " "
            else:
                bullets.append(stripped)

        return {"topic": prompt.strip(), "bullets": bullets}

    def _extract_part3(self, search_text: str) -> list[str]:
        m2 = re.search(r"(?i)(PART\s+2\b|Describe\s+a\b|Talk\s+about\b)", search_text)
        if not m2:
            return []

        block2 = search_text[m2.start() :]
        m3 = re.search(r"(?i)(PART\s+3\b)", block2)
        if m3:
            block3 = block2[m3.start() :]
        else:
            lines = block2.splitlines()
            start_idx = 0
            for i, line in enumerate(lines):
                if i > 0 and "?" in line:
                    start_idx = i
                    if (
                        i > 1
                        and len(lines[i - 1].split()) <= 4
                        and not lines[i - 1].endswith(".")
                    ):
                        start_idx = i - 1
                    break
            if start_idx == 0:
                return []
            block3 = "\n".join(lines[start_idx:])

        questions = []
        for line in block3.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"(?i)^(part 3|discussion|speaking test)", stripped):
                continue
            if "?" in stripped or re.match(r"^\d+[.)]\s+", stripped):
                cleaned = re.sub(r"^\d+[.)]\s+", "", stripped)
                if cleaned:
                    questions.append(cleaned)
        return questions
