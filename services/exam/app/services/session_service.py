import json
import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.core.exam_observability import record_exam_completion
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
from app.services.audio_delivery_service import (
    ListeningAudioUnavailableError,
    S3AudioDeliveryService,
)
from app.services.writing_image_delivery_service import (
    S3WritingImageDeliveryService,
    WritingImageUnavailableError,
)
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
        image_delivery_service: S3WritingImageDeliveryService | None = None,
    ):
        self.session_repository = session_repository
        self.question_repository = question_repository
        self.result_repository = result_repository
        self.timer_service = timer_service or TimerService()
        self.grading_service = grading_service or GradingService()
        self.writing_response_repository = writing_response_repository
        self.writing_client = writing_client
        self.audio_delivery_service = audio_delivery_service
        self.image_delivery_service = image_delivery_service

    async def create_session(
        self,
        request: CreateSessionRequest,
    ) -> dict[str, Any]:
        question = await self.question_repository.get_random_question(
            exam_type=request.exam_type.value,
            skill_area=request.skill_area.value,
            user_id=request.user_id,
        )
        # Academic and General Training use the same Speaking interview. The
        # current bank predates General rows, so reuse a Speaking set rather
        # than making General candidates fail before the live interviewer (the
        # source of the questions used during the socket) can start.
        if question is None and request.skill_area.value == "speaking":
            question = await self.question_repository.get_random_question(
                exam_type="academic",
                skill_area="speaking",
                user_id=request.user_id,
            )
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found",
            )

        session_id = uuid4()
        time_limit_seconds = self._time_limit_for(request.skill_area.value)

        # Refuse a broken Academic Writing Task 1 before any state exists.
        # Computing the URL here -- ahead of the session row -- means a missing
        # stimulus image costs the candidate nothing: no row, no clock, retry
        # later. Serving the prompt without its chart would be worse than
        # refusing, because the task is literally "describe the chart" (BUG-022
        # shape). NULL image_s3_key (every non-visual task) returns None and is
        # untouched.
        image_url = self._require_image_url(question, session_id)

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
            "first_question_set": self._public_question(question, image_url=image_url),
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

        # Best-effort on the read path: presigned URLs expire (7200s) and are
        # never persisted, so a page reload mid-exam has to re-mint one. Unlike
        # session start this must NOT refuse -- get_session also backs the submit
        # flow (sessions.py reads it for metrics), and a chart that vanished
        # mid-attempt should not block the candidate from submitting what they
        # already wrote. A missing image degrades to image_url=None here.
        image_url = self._optional_image_url(question, session["id"])

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
            "questions": [self._public_question(question, image_url=image_url)],
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

        record_exam_completion(
            session_id=session_id,
            user_id=session["user_id"],
            skill_area=session["skill_area"],
            exam_type=session["exam_type"],
            band_score=grading["band_score"],
            duration_s=self.timer_service.elapsed_seconds(session["started_at"]),
            question_bank_ref=question.get("book_ref"),
        )

        return {
            "session_id": session_id,
            "status": "submitted",
            "raw_score": grading["raw_score"],
            "band_score": grading["band_score"],
        }

    async def get_result(self, session_id: UUID, requester_id: UUID) -> dict[str, Any]:
        session = await self.session_repository.get_by_id(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        if str(session["user_id"]) != str(requester_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session belongs to another user",
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

        record_exam_completion(
            session_id=session_id,
            user_id=session["user_id"],
            skill_area="reading",
            exam_type=session["exam_type"],
            band_score=grading["band_score"],
            duration_s=self.timer_service.elapsed_seconds(session["started_at"]),
            question_bank_ref=question.get("book_ref"),
        )

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
        except ListeningAudioUnavailableError as exc:
            # 503, not 500: the key is well-formed and this code is correct --
            # the audio was simply never uploaded. Refusing here means no session
            # row and no 40-minute clock, so the candidate can retry later rather
            # than burning an attempt on a test that cannot play (BUG-022).
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
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

        record_exam_completion(
            session_id=session_id,
            user_id=session["user_id"],
            skill_area="listening",
            exam_type=session["exam_type"],
            band_score=grading["band_score"],
            duration_s=self.timer_service.elapsed_seconds(session["started_at"]),
            question_bank_ref=question.get("book_ref"),
        )

        return grading

    def _time_limit_for(self, skill_area: str) -> int:
        return self.DEFAULT_TIME_LIMITS_SECONDS[skill_area]

    def _require_image_url(self, question: Any, session_id: UUID) -> str | None:
        """Mint the Task 1 stimulus URL, refusing the session if it can't be served.

        Returns None when the question carries no image (the common case: every
        non-visual task). When it does carry one, a failure to produce a usable
        URL is fatal here -- raised as an HTTPException so no session row is
        created -- because serving "describe the chart" without the chart is a
        broken exam, not a degraded one.
        """
        image_s3_key = question.get("image_s3_key")
        if not image_s3_key:
            return None

        if self.image_delivery_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Writing image delivery is not configured",
            )

        try:
            return self.image_delivery_service.generate_image_url(
                image_s3_key=image_s3_key,
                session_id=session_id,
            )
        except WritingImageUnavailableError as exc:
            # 503, not 500: the key is well-formed and this code is correct --
            # the image was simply never uploaded. Same reasoning as the
            # listening audio guard (BUG-022): refuse before creating state.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    def _optional_image_url(self, question: Any, session_id: UUID) -> str | None:
        """Mint the Task 1 stimulus URL on the read path, degrading to None.

        The read/submit path must never raise on a missing image (see
        get_session), so every failure -- unconfigured service, missing object,
        malformed key -- collapses to None. Start-of-session already refused the
        genuinely broken cases; this only re-mints an expiring URL.
        """
        image_s3_key = question.get("image_s3_key")
        if not image_s3_key or self.image_delivery_service is None:
            return None

        try:
            return self.image_delivery_service.generate_image_url(
                image_s3_key=image_s3_key,
                session_id=session_id,
            )
        except Exception:
            return None

    def _public_question(
        self, question: Any, image_url: str | None = None
    ) -> dict[str, Any]:
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
            "image_s3_key": question.get("image_s3_key"),
            "image_url": image_url,
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
        # A response row exists as soon as save_response() runs, *before*
        # the (possibly failing) evaluation call -- so a task whose
        # evaluation previously failed still has a row here. Checking row
        # presence alone previously let a retried task be considered
        # "submitted" for the *other* task's response, prematurely flipping
        # the whole session to "submitted"/"scored" while that other task
        # had no real evaluation yet, then rejecting its own legitimate
        # retry with 400 "Invalid session state". Require a completed
        # evaluation on both tasks instead.
        all_tasks_submitted = {1, 2}.issubset(
            {
                r["task_number"]
                for r in responses
                if r["evaluation_result"] is not None
            }
        )

        if all_tasks_submitted:
            await self.session_repository.submit(session_id)
            await self.session_repository.mark_scored(session_id)

            overall_band = self._writing_overall_band(responses)
            question = await self.question_repository.get_by_id(
                session["question_id"]
            )
            record_exam_completion(
                session_id=session_id,
                user_id=session["user_id"],
                skill_area="writing",
                exam_type=session["exam_type"],
                band_score=overall_band,
                duration_s=self.timer_service.elapsed_seconds(session["started_at"]),
                question_bank_ref=question.get("book_ref") if question else None,
            )

        return {
            "session_id": session_id,
            "task_number": request.task_number,
            "status": "submitted" if all_tasks_submitted else "task_submitted",
            "overall_band": evaluation.overall_band,
            "word_count": word_count,
            "penalty_flag": penalty_flag,
            # The per-criterion breakdown is computed above and persisted on the
            # line before this, but used to be dropped on the way out — leaving
            # no way for a client to show Task 1 feedback while Task 2 is still
            # being written. GET /{session_id}/result cannot fill that gap: it
            # 404s until both task rows exist (see _get_writing_result), by
            # design, because a "result" for half a paper is not a result.
            # Additive, so existing callers are unaffected (GOA-058).
            "evaluations": [
                item.model_dump() for item in evaluation.evaluations
            ],
        }

    async def _resolve_task_context(
        self,
        session: dict[str, Any],
        task_number: int,
    ) -> tuple[str | None, str | None]:
        """
        Find the prompt for one writing task.

        `questions` is stored as JSONB and two different shapes are genuinely in
        use, so this must handle both:

          A) a LIST, one entry per task, each carrying its own `number`. This is
             what every ingested Cambridge book produces
             (app/ingestion/writing_parser.py) and therefore what real sessions
             actually contain.

          B) a DICT keyed `task1`/`task2`. Used by seeded/fixture data.

        This method previously assumed shape B unconditionally and called .get()
        on the decoded value. A non-empty list is truthy, so `questions_data or
        {}` left it a list and `.get` raised AttributeError — an unhandled
        exception, i.e. HTTP 500 on *every* writing submit against real data,
        for both tasks. Shape A is now handled first because it is the common
        case in production.

        Returns (task_prompt, stimulus_s3_key). The second element is always
        None today — see the TODO below.
        """
        question = await self.question_repository.get_by_id(session["question_id"])

        if question is None:
            return None, None

        # _question_list already normalises str/dict/list JSONB into a list and
        # is the same helper _public_question uses, so the submit path and the
        # read path can never disagree about what the question contains.
        entries = self._question_list(question["questions"])
        task_data: dict[str, Any] = {}

        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue

            # Shape B arrives wrapped in a single-element list.
            nested = entry.get(f"task{task_number}")
            if isinstance(nested, dict):
                task_data = nested
                break

            # Shape A: trust the declared `number` when present so array order
            # alone cannot swap the two tasks; fall back to position.
            number = entry.get("number", index + 1)
            if number == task_number:
                task_data = entry
                break

        task_prompt = task_data.get("prompt")

        # TODO(GOA-058 follow-up): reintroduce the Academic Task 1 stimulus
        # image here once the ingestion + S3 pre-signing pipeline exists. The
        # plumbing below is intentionally left in place (the Writing service
        # still accepts an optional `stimulusS3Key`) so restoring it is a
        # one-line change:
        #     stimulus_s3_key = task_data.get("image_s3_key") if task_number == 1 else None
        # Image-based evaluation is postponed: no ingested question carries an
        # image key and the current Writing agents no longer consume one.
        stimulus_s3_key = None

        return task_prompt, stimulus_s3_key

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
        overall_band = self._weight_writing_bands(band_task1, band_task2)

        return {
            "session_id": session_id,
            "user_id": session["user_id"],
            "skill_area": "writing",
            "overall_band": overall_band,
            "tasks": tasks,
        }

    def _weight_writing_bands(self, band_task1: float, band_task2: float) -> float:
        # IELTS weighting: Task 2 counts twice Task 1, rounded to nearest 0.5.
        return round((band_task1 + 2 * band_task2) / 3 * 2) / 2

    def _writing_overall_band(self, responses: list[Any]) -> float:
        """Overall writing band from the two stored task evaluations.

        Shares ``_weight_writing_bands`` with ``_get_writing_result`` so the
        completion log and the result endpoint never disagree.
        """

        bands: dict[int, float] = {}
        for r in responses:
            evaluation = self._decode_json(r["evaluation_result"]) or {}
            bands[r["task_number"]] = evaluation.get("overall_band", 0.0)
        return self._weight_writing_bands(bands.get(1, 0.0), bands.get(2, 0.0))
