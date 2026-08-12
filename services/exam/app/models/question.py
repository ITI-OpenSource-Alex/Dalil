from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass(slots=True)
class Question:
    id: UUID
    book_ref: str
    test_number: int
    exam_type: str
    skill_area: str
    passage_text: Optional[str]
    audio_s3_key: Optional[str]
    # S3 key of the Academic Writing Task 1 stimulus image (chart/graph/map).
    # NULL for every other question type -- see migration 009.
    image_s3_key: Optional[str]
    questions: dict
    answer_key: dict
