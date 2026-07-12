import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.repositories.question_repository import QuestionRepository
from app.repositories.result_repository import ResultRepository
from app.repositories.session_repository import SessionRepository
from app.schemas import CreateSessionRequest, SubmitAnswersRequest
from app.schemas.question import QuestionResponse
from app.services.grading_service import GradingService
from app.services.timer_service import TimerService


class SessionService:
    DEFAULT_TIME_LIMITS_SECONDS = {
        "listening": 30 * 60,
        "reading": 60 * 60,
        "writing": 60 * 60,
        "speaking": 15 * 60,
    }

    def __init__(
        self,
        session_repository: SessionRepository,
        question_repository: QuestionRepository,
        result_repository: ResultRepository,
        timer_service: TimerService | None = None,
        grading_service: GradingService | None = None,
    ):
        self.session_repository = session_repository
        self.question_repository = question_repository
        self.result_repository = result_repository
        self.timer_service = timer_service or TimerService()
        self.grading_service = grading_service or GradingService()

    async def create_session(
        self,
        request: CreateSessionRequest,
    ) -> dict[str, Any]:
        question = await self.question_repository.get_random_question(
            exam_type=request.exam_type.value,
            skill_area=request.skill_area.value,
        )
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            )

        session_id = uuid4()
        time_limit_seconds = self._time_limit_for(request.skill_area.value)

        await self.session_repository.create(
            session_id=session_id,
            user_id=request.user_id,
            question_id=question["id"],
            exam_type=request.exam_type.value,
            skill_area=request.skill_area.value,
            status="in_progress",
            time_limit_seconds=time_limit_seconds,
        )

        return {
            "session_id": session_id,
            "first_question_set": self._public_question(question),
        }

    async def get_session(self, session_id: UUID) -> dict[str, Any]:
        session = await self.session_repository.get_by_id(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        question = await self.question_repository.get_by_id(session["question_id"])
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            )

        return {
            "id": session["id"],
            "user_id": session["user_id"],
            "exam_type": session["exam_type"],
            "skill_area": session["skill_area"],
            "status": session["status"],
            "started_at": session["started_at"],
            "submitted_at": session["submitted_at"],
            "time_limit_seconds": session["time_limit_seconds"],
            "remaining_seconds": self.timer_service.remaining_time(
                session["started_at"],
                session["time_limit_seconds"],
            ),
            "questions": [self._public_question(question)],
        }

    async def submit_session(
        self,
        session_id: UUID,
        request: SubmitAnswersRequest,
    ) -> dict[str, Any]:
        session = await self.session_repository.get_by_id(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        if session["status"] != "in_progress":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session state",
            )

        if self.timer_service.is_expired(
            session["started_at"],
            session["time_limit_seconds"],
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session expired",
            )

        question = await self.question_repository.get_by_id(session["question_id"])
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            )
        answer_key = self._decode_json(question["answer_key"])

        grading = self.grading_service.grade(
            submitted_answers=request.answers,
            answer_key=answer_key,
            skill_area=session["skill_area"],
        )

        await self.result_repository.create(
            result_id=uuid4(),
            session_id=session_id,
            user_id=session["user_id"],
            skill_area=session["skill_area"],
            raw_score=grading["raw_score"],
            band_score=grading["band_score"],
            section_scores=grading["section_scores"],
        )
        await self.session_repository.submit(session_id)
        await self.session_repository.mark_scored(session_id)

        return {
            "session_id": session_id,
            "status": "submitted",
            "raw_score": grading["raw_score"],
            "band_score": grading["band_score"],
        }

    async def get_result(self, session_id: UUID) -> dict[str, Any]:
        session = await self.session_repository.get_by_id(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        if session["status"] not in {"submitted", "scored"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session state",
            )

        result = await self.result_repository.get_by_session(session_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Result not found",
            )

        question = await self.question_repository.get_by_id(session["question_id"])
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            )
        answer_key = self._decode_json(question["answer_key"])

        return {
            "id": result["id"],
            "session_id": result["session_id"],
            "user_id": result["user_id"],
            "skill_area": result["skill_area"],
            "raw_score": result["raw_score"],
            "band_score": float(result["band_score"]),
            "section_scores": self._decode_json(result["section_scores"]) or {},
            "graded_at": result["graded_at"],
            "answer_key": answer_key,
        }

    def _time_limit_for(self, skill_area: str) -> int:
        return self.DEFAULT_TIME_LIMITS_SECONDS[skill_area]

    def _public_question(self, question: Any) -> dict[str, Any]:
        payload = {
            "id": question["id"],
            "book_ref": question["book_ref"],
            "test_number": question["test_number"],
            "exam_type": question["exam_type"],
            "skill_area": question["skill_area"],
            "passage_text": question["passage_text"],
            "audio_s3_key": question["audio_s3_key"],
            "questions": self._question_list(question["questions"]),
        }
        return QuestionResponse.model_validate(payload).model_dump()

    def _question_list(self, value: Any) -> list[dict[str, Any]]:
        decoded = self._decode_json(value)
        if decoded is None:
            return []
        if isinstance(decoded, list):
            return decoded
        if isinstance(decoded, dict):
            nested_questions = decoded.get("questions")
            if isinstance(nested_questions, list):
                return nested_questions
            return [decoded]
        return []

    def _decode_json(self, value: Any) -> Any:
        if isinstance(value, str):
            return json.loads(value)
        return value
