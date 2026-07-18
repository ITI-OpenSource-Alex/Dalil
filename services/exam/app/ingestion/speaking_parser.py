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

        part1 = self._extract_part1(text)
        part2 = self._extract_part2(text)
        part3 = self._extract_part3(text)

        questions: list[dict[str, Any]] = []
        q_number = 1

        for topic in part1:
            questions.append({
                "number": q_number,
                "prompt": topic,
                "question_type": "Speaking Part 1",
                "instructions": "Answer the question in 1-2 sentences.",
                "passage_number": None,
                "section_number": 1,
            })
            q_number += 1

        if part2:
            questions.append({
                "number": q_number,
                "prompt": part2["topic"],
                "question_type": "Speaking Part 2",
                "instructions": "Speak for 1-2 minutes on this topic.",
                "passage_number": None,
                "section_number": 2,
                "bullet_points": part2.get("bullets", []),
            })
            q_number += 1

        for discussion_q in part3:
            questions.append({
                "number": q_number,
                "prompt": discussion_q,
                "question_type": "Speaking Part 3",
                "instructions": "Discuss this question in detail.",
                "passage_number": None,
                "section_number": 3,
            })
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

    def _extract_part1(self, text: str) -> list[str]:
        pattern = re.compile(
            r"(?i)PART\s+1\b(.*?)(?=PART\s+[23]\b|$)", re.DOTALL
        )
        m = pattern.search(text)
        if not m:
            return []

        block = m.group(1).strip()
        questions = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"(?i)^(the examiner|introduction|let)", stripped):
                continue
            if stripped.endswith("?") or re.match(r"^\d+[.)]\s+", stripped):
                cleaned = re.sub(r"^\d+[.)]\s+", "", stripped)
                if cleaned:
                    questions.append(cleaned)

        return questions

    def _extract_part2(self, text: str) -> dict[str, Any] | None:
        pattern = re.compile(
            r"(?i)PART\s+2\b(.*?)(?=PART\s+3\b|$)", re.DOTALL
        )
        m = pattern.search(text)
        if not m:
            return None

        block = m.group(1).strip()
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

        topic = ""
        bullets: list[str] = []
        found_describe = False

        for line in lines:
            if re.match(r"(?i)^(the examiner|you will have|you should say)", line):
                continue
            if re.match(r"(?i)^(describe|talk about|you should)", line):
                topic = line
                found_describe = True
                continue
            if found_describe and re.match(r"^[-•·*]\s*", line):
                bullet = re.sub(r"^[-•·*]\s*", "", line).strip()
                if bullet:
                    bullets.append(bullet)
            elif found_describe and re.match(r"(?i)^(and\s+)?(explain|say)\b", line):
                bullets.append(line)

        if not topic and lines:
            topic = lines[0]

        return {"topic": topic, "bullets": bullets} if topic else None

    def _extract_part3(self, text: str) -> list[str]:
        pattern = re.compile(
            r"(?i)PART\s+3\b(.*?)(?=PART\s+\d|SPEAKING\s+TEST|$)", re.DOTALL
        )
        m = pattern.search(text)
        if not m:
            return []

        block = m.group(1).strip()
        questions = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"(?i)^(the examiner|discussion)", stripped):
                continue
            if stripped.endswith("?") or re.match(r"^\d+[.)]\s+", stripped):
                cleaned = re.sub(r"^\d+[.)]\s+", "", stripped)
                if cleaned:
                    questions.append(cleaned)

        return questions
