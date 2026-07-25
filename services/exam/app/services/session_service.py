import json
import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.core.metrics import (
    goa_writing_exam_task1_evaluation_ms,
    goa_writing_exam_task2_evaluation_ms,
)
from app.repositories.question_repository import QuestionRepository
from app.repositories.result_repository import ResultRepository
from app.repositories.session_repository import SessionRepository
from app.schemas import CreateSessionRequest, SubmitAnswersRequest
from app.schemas.question import QuestionResponse
from app.services.grading_service import GradingService
from app.services.audio_delivery_service import S3AudioDeliveryService
from app.services.timer_service import TimerService
from app.repositories.writing_response_repository import WritingResponseRepository
from app.services.writing_client import WritingClient, WritingServiceError


class SessionService:
    DEFAULT_TIME_LIMITS_SECONDS = {
        "listening": 40 * 60,
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
        writing_response_repository: WritingResponseRepository | None = None,
        writing_client: WritingClient | None = None,
        audio_delivery_service: S3AudioDeliveryService | None = None,
    ):
        self.session_repository = session_repository
        self.question_repository = question_repository
        self.result_repository = result_repository
        self.timer_service = timer_service or TimerService()
        self.grading_service = grading_service or GradingService()
        self.writing_response_repository = writing_response_repository
        self.writing_client = writing_client
        self.audio_delivery_service = audio_delivery_service

    async def create_session(
        self,
        request: CreateSessionRequest,
    ) -> dict[str, Any]:
        question = await self.question_repository.get_random_question(
            exam_type=request.exam_type.value,
            skill_area=request.skill_area.value,
            user_id=request.user_id,
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

        if session["status"] == "abandoned":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session abandoned",
            )

        if session["status"] != "in_progress":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session state",
            )

        if session["skill_area"] == "writing":
            return await self._submit_writing(session_id, session, request)

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

        if session["skill_area"] == "writing":
            return await self._get_writing_result(session_id, session)

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

    async def create_reading_session(
        self,
        user_id: UUID,
        exam_type: str,
    ) -> dict[str, Any]:
        question = await self.question_repository.get_random_unseen_question(
            exam_type=exam_type,
            skill_area="reading",
            user_id=user_id,
        )
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No reading tests available",
            )

        session_id = uuid4()
        time_limit_seconds = self._time_limit_for("reading")

        await self.session_repository.create(
            session_id=session_id,
            user_id=user_id,
            question_id=question["id"],
            exam_type=exam_type,
            skill_area="reading",
            status="in_progress",
            time_limit_seconds=time_limit_seconds,
        )

        passage_text = question["passage_text"] or ""
        passages = [p.strip() for p in passage_text.split("---") if p.strip()]
        questions_data = self._question_list(question["questions"])

        return {
            "session_id": session_id,
            "passages": passages,
            "questions": questions_data,
            "time_limit_seconds": time_limit_seconds,
        }

    async def submit_reading_session(
        self,
        session_id: UUID,
        answers: dict[str, str],
    ) -> dict[str, Any]:
        session = await self.session_repository.get_by_id(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        if session["status"] == "abandoned":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session abandoned",
            )

        if session["status"] in {"submitted", "scored"}:
            existing = await self.result_repository.get_by_session(session_id)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Session already submitted",
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

        grading = self.grading_service.grade_reading(
            submitted_answers=answers,
            answer_key=answer_key,
            exam_type=session["exam_type"],
        )

        await self.result_repository.create(
            result_id=uuid4(),
            session_id=session_id,
            user_id=session["user_id"],
            skill_area="reading",
            raw_score=grading["raw_score"],
            band_score=grading["band_score"],
            section_scores=grading["section_breakdown"],
        )
        await self.session_repository.submit(session_id)
        await self.session_repository.mark_scored(session_id)

        return grading

    async def create_listening_session(
        self,
        user_id: UUID,
        exam_type: str,
    ) -> dict[str, Any]:
        question = await self.question_repository.get_random_unseen_question(
            exam_type=exam_type,
            skill_area="listening",
            user_id=user_id,
        )
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No unseen listening tests available",
            )
        if self.audio_delivery_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Listening audio delivery is not configured",
            )

        session_id = uuid4()
        time_limit_seconds = self._time_limit_for("listening")
        try:
            audio_urls = self.audio_delivery_service.generate_section_urls(
                audio_s3_key=question["audio_s3_key"],
                session_id=session_id,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

        await self.session_repository.create(
            session_id=session_id,
            user_id=user_id,
            question_id=question["id"],
            exam_type=exam_type,
            skill_area="listening",
            status="in_progress",
            time_limit_seconds=time_limit_seconds,
        )

        return {
            "session_id": session_id,
            "audio_urls": audio_urls,
            "questions": self._question_list(question["questions"]),
            "time_limit_seconds": time_limit_seconds,
            "audio_url_expiry_seconds": (
                self.audio_delivery_service.PRESIGNED_URL_EXPIRY_SECONDS
            ),
        }

    async def submit_listening_session(
        self,
        session_id: UUID,
        user_id: UUID,
        answers: dict[str, str],
    ) -> dict[str, Any]:
        session = await self.session_repository.get_by_id(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        if str(session["user_id"]) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session belongs to another user",
            )
        if session["skill_area"] != "listening":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session is not a listening exam",
            )
        if session["status"] == "abandoned":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session abandoned",
            )
        if session["status"] in {"submitted", "scored"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session already submitted",
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
        grading = self.grading_service.grade_listening(
            submitted_answers=answers,
            answer_key=self._decode_json(question["answer_key"]),
        )

        await self.result_repository.create(
            result_id=uuid4(),
            session_id=session_id,
            user_id=session["user_id"],
            skill_area="listening",
            raw_score=grading["raw_score"],
            band_score=grading["band_score"],
            section_scores=grading["section_breakdown"],
        )
        await self.session_repository.submit(session_id)
        await self.session_repository.mark_scored(session_id)
        return grading

    def _time_limit_for(self, skill_area: str) -> int:
        return self.DEFAULT_TIME_LIMITS_SECONDS[skill_area]

    def _public_question(self, question: Any) -> dict[str, Any]:
        questions_data = self._question_list(question["questions"])
        if question["skill_area"] == "speaking":
            questions_data = self._shape_speaking_questions(questions_data)
        payload = {
            "id": question["id"],
            "book_ref": question["book_ref"],
            "test_number": question["test_number"],
            "exam_type": question["exam_type"],
            "skill_area": question["skill_area"],
            "passage_text": question["passage_text"],
            "audio_s3_key": question["audio_s3_key"],
            "questions": questions_data,
        }
        return QuestionResponse.model_validate(payload).model_dump()

    def _shape_speaking_questions(
        self, raw_questions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        parts = [
            {"part": 1, "type": "general", "questions": []},
            {"part": 2, "type": "cue_card", "topic": "", "bullet_points": []},
            {"part": 3, "type": "discussion", "questions": []},
        ]

        for item in raw_questions:
            part = item.get("part")

            if part == 1:
                questions = item.get("questions", [])
                if isinstance(questions, list):
                    parts[0]["questions"].extend(questions)
                elif isinstance(questions, str):
                    parts[0]["questions"].append(questions)
            elif part == 2:
                if not parts[1]["topic"]:
                    parts[1]["topic"] = item.get("topic", "")

                bullets = item.get("bullet_points", [])
                if isinstance(bullets, list):
                    parts[1]["bullet_points"].extend(bullets)

            elif part == 3:
                questions = item.get("questions", [])
                if isinstance(questions, list):
                    parts[2]["questions"].extend(questions)
                elif isinstance(questions, str):
                    parts[2]["questions"].append(questions)

        return parts

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

    # The session only flips to submitted/scored once both task rows exist
    # so the frontend's first PUT /submit call for Task 1 gets back "status": "task_submitted",
    # and the second (Task 2) gets "status": "submitted". Your GET /{session_id}
    # and GET /{session_id}/result status checks ({"submitted", "scored"}) keep working unchanged.

    async def _submit_writing(
        self,
        session_id: UUID,
        session: dict[str, Any],
        request: SubmitAnswersRequest,
    ) -> dict[str, Any]:
        if request.task_number is None or request.essay_text is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="essay_text and task_number are required for writing submissions",
            )
        if self.writing_response_repository is None or self.writing_client is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Writing submission is not configured",
            )

        word_count = len(request.essay_text.split())
        penalty_flag = (request.task_number == 1 and word_count < 150) or (
            request.task_number == 2 and word_count < 250
        )
        await self.writing_response_repository.save_response(
            session_id=session_id,
            task_number=request.task_number,
            response_text=request.essay_text,
            word_count=word_count,
            penalty_flag=penalty_flag,
        )

        task_prompt, stimulus_s3_key = await self._resolve_task_context(
            session, request.task_number
        )

        task_histogram = (
            goa_writing_exam_task1_evaluation_ms
            if request.task_number == 1
            else goa_writing_exam_task2_evaluation_ms
        )
        started = time.perf_counter()
        try:
            evaluation = await self.writing_client.evaluate_exam_essay(
                user_id=str(session["user_id"]),
                essay_text=request.essay_text,
                exam_type=session["exam_type"],
                exam_session_id=session_id,
                task_number=request.task_number,
                stimulus_s3_key=stimulus_s3_key,
                task_prompt=task_prompt,
            )
        except WritingServiceError as exc:
            task_histogram.observe((time.perf_counter() - started) * 1000)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        task_histogram.observe((time.perf_counter() - started) * 1000)

        await self.writing_response_repository.save_evaluation(
            session_id=session_id,
            task_number=request.task_number,
            evaluation_result=evaluation.model_dump(),
        )

        responses = await self.writing_response_repository.get_all_by_session(
            session_id
        )
        all_tasks_submitted = {1, 2}.issubset({r["task_number"] for r in responses})

        if all_tasks_submitted:
            await self.session_repository.submit(session_id)
            await self.session_repository.mark_scored(session_id)

        return {
            "session_id": session_id,
            "task_number": request.task_number,
            "status": "submitted" if all_tasks_submitted else "task_submitted",
            "overall_band": evaluation.overall_band,
            "word_count": word_count,
            "penalty_flag": penalty_flag,
        }

    async def _resolve_task_context(
        self,
        session: dict[str, Any],
        task_number: int,
    ) -> tuple[str | None, str | None]:
        question = await self.question_repository.get_by_id(session["question_id"])

        if question is None:
            return None, None
        questions_data = self._decode_json(question["questions"])
        task_key = "task1" if task_number == 1 else "task2"
        task_data = (questions_data or {}).get(task_key, {})
        task_prompt = task_data.get("prompt")
        image_s3_key = task_data.get("image_s3_key") if task_number == 1 else None
        return task_prompt, image_s3_key

    async def _get_writing_result(
        self,
        session_id: UUID,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        responses = await self.writing_response_repository.get_all_by_session(
            session_id
        )
        if len(responses) < 2:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Result not found",
            )

        tasks: dict[int, dict[str, Any]] = {}
        for r in responses:
            tasks[r["task_number"]] = {
                "response_text": r["response_text"],
                "word_count": r["word_count"],
                "penalty_flag": bool(r["penalty_flag"])
                if "penalty_flag" in r.keys()
                else False,
                "evaluation": self._decode_json(r["evaluation_result"]) or {},
            }

        band_task1 = tasks.get(1, {}).get("evaluation", {}).get("overall_band", 0.0)
        band_task2 = tasks.get(2, {}).get("evaluation", {}).get("overall_band", 0.0)
        # IELTS weighting: Task 2 counts twice Task 1. Confirm this is what you want.
        overall_band = round((band_task1 + 2 * band_task2) / 3 * 2) / 2  # nearest 0.5

        return {
            "session_id": session_id,
            "user_id": session["user_id"],
            "skill_area": "writing",
            "overall_band": overall_band,
            "tasks": tasks,
        }
