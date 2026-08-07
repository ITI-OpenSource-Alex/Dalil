import hashlib
import json

from sqlalchemy.orm import Session

from app.config import Settings
from app.evaluation import EvaluationSummary
from app.models import Essay
from app.schemas import CriterionEvaluation


def evaluation_cache_key(
    essay_text: str,
    submission_type: str,
    exam_type: str,
    settings: Settings,
) -> str:
    canonical = json.dumps(
        {
            "cache_version": settings.cache_version,
            "model": settings.writing_model,
            "essay_text": essay_text,
            "submission_type": submission_type,
            "exam_type": exam_type,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find_cached_evaluation(db: Session, cache_key: str, user_id: str) -> dict | None:
    # Scoped by user_id, not just cache_key: the key is a hash of essay text +
    # submission/exam type only, so two users submitting identical text would
    # otherwise be served each other's cached evaluation row.
    essay = (
        db.query(Essay)
        .filter(
            Essay.evaluation_cache_key == cache_key,
            Essay.evaluation_result.isnot(None),
            Essay.user_id == user_id,
        )
        .order_by(Essay.id.desc())
        .first()
    )
    return essay.evaluation_result if essay else None


def parse_cached_evaluations(payload: dict) -> list[CriterionEvaluation]:
    return [
        CriterionEvaluation.model_validate(item)
        for item in payload.get("evaluations", [])
    ]


def persist_evaluation(db: Session, essay: Essay, summary: EvaluationSummary) -> None:
    essay.evaluation_result = {
        "evaluations": [item.model_dump() for item in summary.evaluations],
        "overall_band": summary.overall_band,
    }
    essay.status = "evaluated"
    db.add(essay)
    db.commit()
    db.refresh(essay)
