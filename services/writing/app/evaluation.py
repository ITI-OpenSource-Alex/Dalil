import asyncio
import inspect
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from typing import Any, Awaitable, Callable

from app.agents import (
    CRITERIA,
    AgentExecution,
    Criterion,
    FeedbackExecution,
    ScoreExecution,
    WritingAgentRunner,
    get_agent_runner,
)
from app.metrics import AGENT_BAND_SCORE
from app.ocr_normalization import InputSource, normalize_essay
from app.schemas import CriterionEvaluation
from app.agents import TaskNumber, extract_chart_context


PartialCallback = Callable[[CriterionEvaluation], Awaitable[None] | None]


@dataclass(frozen=True)
class EvaluationSummary:
    evaluations: list[CriterionEvaluation]
    overall_band: float
    total_tokens: int
    total_cost_usd: float


class EvaluationFailed(RuntimeError):
    pass


def calculate_overall_band(band_scores: list[float]) -> float:
    if len(band_scores) != 4:
        raise ValueError("Overall IELTS Writing band requires exactly four scores")
    mean = sum(Decimal(str(score)) for score in band_scores) / Decimal("4")
    return float((mean * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2)


def _span(
    trace: Any,
    criterion: Criterion,
    *,
    from_cache: bool,
    model: str,
) -> Any:
    if trace is None:
        return None
    try:
        return trace.start_observation(
            name=f"writing-{criterion}",
            as_type="generation",
            model=model,
            input={"criterion": criterion, "from_cache": from_cache},
        )
    except Exception:
        return None


def _end_span(span: Any, execution: AgentExecution, *, from_cache: bool) -> None:
    if span is None:
        return
    metadata = {
        "criterion": execution.result.criterion,
        "band_score": execution.result.band_score,
        "prompt_tokens": execution.prompt_tokens,
        "completion_tokens": execution.completion_tokens,
        "latency_ms": execution.latency_ms,
        "from_cache": from_cache,
    }
    try:
        span.update(
            output=execution.result.model_dump(),
            metadata=metadata,
            usage_details={
                "input": execution.prompt_tokens,
                "output": execution.completion_tokens,
            },
        )
        span.end()
    except Exception:
        pass


def _end_score_span(
    span: Any,
    execution: ScoreExecution,
    *,
    previous: ScoreExecution | None = None,
) -> None:
    if span is None:
        return
    try:
        input_tokens = execution.prompt_tokens - (
            previous.prompt_tokens if previous else 0
        )
        output_tokens = execution.completion_tokens - (
            previous.completion_tokens if previous else 0
        )
        model_calls = execution.model_calls - (
            previous.model_calls if previous else 0
        )
        latency_ms = execution.latency_ms - (
            previous.latency_ms if previous else 0.0
        )
        span.update(
            output={
                "criterion": execution.criterion,
                "band_score": execution.band_score,
                "descriptor_id": execution.decision.descriptor_id,
                "confidence": execution.decision.confidence,
            },
            metadata={
                "criterion": execution.criterion,
                "stage": "score",
                "model_calls": model_calls,
                "ensemble_used": execution.ensemble_used,
                "latency_ms": latency_ms,
            },
            usage_details={
                "input": input_tokens,
                "output": output_tokens,
            },
        )
        span.end()
    except Exception:
        pass


def _feedback_span(trace: Any, *, model: str, criteria: list[Criterion]) -> Any:
    if trace is None:
        return None
    try:
        return trace.start_observation(
            name="writing-feedback",
            as_type="generation",
            model=model,
            input={"criteria": criteria, "stage": "feedback"},
        )
    except Exception:
        return None


def _end_feedback_span(span: Any, execution: FeedbackExecution) -> None:
    if span is None:
        return
    try:
        span.update(
            output={"criteria": list(execution.evaluations)},
            metadata={
                "stage": "feedback",
                "model_calls": execution.model_calls,
                "latency_ms": execution.latency_ms,
            },
            usage_details={
                "input": execution.prompt_tokens,
                "output": execution.completion_tokens,
            },
        )
        span.end()
    except Exception:
        pass


async def _notify(callback: PartialCallback | None, result: CriterionEvaluation) -> None:
    if callback is None:
        return
    maybe_awaitable = callback(result)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


class EvaluationCoordinator:
    def __init__(self, runner: WritingAgentRunner) -> None:
        self.runner = runner

    async def evaluate(
        self,
        essay_text: str,
        exam_type: str,
        *,
        user_id: str = "anonymous",
        trace: Any = None,
        on_partial: PartialCallback | None = None,
        input_source: InputSource = "typed",
    ) -> EvaluationSummary:
        if hasattr(self.runner, "score") and hasattr(self.runner, "generate_feedback"):
            task_number: TaskNumber = (
                1 if "task_1" in exam_type or "task1" in exam_type else 2
            )
            return await self._evaluate_staged(
                essay_text,
                exam_type,
                task_number=task_number,
                user_id=user_id,
                trace=trace,
                on_partial=on_partial,
                input_source=input_source,
            )

        async def run_one(criterion: Criterion) -> AgentExecution:
            child_span = _span(
                trace,
                criterion,
                from_cache=False,
                model=self.runner.model,
            )
            try:
                execution = await self.runner.evaluate(criterion, essay_text, exam_type, user_id=user_id)
                AGENT_BAND_SCORE.labels(criterion=criterion).observe(
                    execution.result.band_score
                )
                _end_span(child_span, execution, from_cache=False)
                await _notify(on_partial, execution.result)
                return execution
            except Exception as exc:
                if child_span is not None:
                    try:
                        child_span.update(
                            level="ERROR",
                            status_message=str(exc),
                            output={"error": str(exc)},
                        )
                        child_span.end()
                    except Exception:
                        pass
                raise

        # This is the one synchronization point for the swarm. The callback lets
        # streaming callers receive each result before gather returns.
        gathered = await asyncio.gather(
            *(run_one(criterion) for criterion in CRITERIA),
            return_exceptions=True,
        )
        failures = [item for item in gathered if isinstance(item, BaseException)]
        if failures:
            raise EvaluationFailed(
                f"{len(failures)} of 4 writing agents failed: {failures[0]}"
            ) from failures[0]

        executions = [item for item in gathered if isinstance(item, AgentExecution)]
        by_criterion = {item.result.criterion: item for item in executions}
        ordered = [by_criterion[criterion] for criterion in CRITERIA]
        evaluations = [item.result for item in ordered]
        return EvaluationSummary(
            evaluations=evaluations,
            overall_band=calculate_overall_band(
                [result.band_score for result in evaluations]
            ),
            total_tokens=sum(
                item.prompt_tokens + item.completion_tokens for item in ordered
            ),
            total_cost_usd=sum(item.cost_usd or 0.0 for item in ordered),
        )

    async def _evaluate_staged(
        self,
        essay_text: str,
        exam_type: str,
        *,
        task_number: TaskNumber,
        user_id: str,
        trace: Any,
        on_partial: PartialCallback | None,
        input_source: InputSource,
        chart_context: str | None = None,
        task_prompt: str | None = None,
    ) -> EvaluationSummary:
        essay = normalize_essay(essay_text, input_source)

        async def run_score(criterion: Criterion) -> ScoreExecution:
            child_span = _span(
                trace,
                criterion,
                from_cache=False,
                model=self.runner.model,
            )
            try:
                execution = await self.runner.score(
                    criterion,
                    essay,
                    exam_type,
                    task_number=task_number,
                    user_id=user_id,
                    chart_context=chart_context,
                    task_prompt=task_prompt,
                    allow_ensemble=False,
                )
                _end_score_span(child_span, execution)
                return execution
            except Exception as exc:
                if child_span is not None:
                    try:
                        child_span.update(
                            level="ERROR",
                            status_message=str(exc),
                            output={"error": str(exc)},
                        )
                        child_span.end()
                    except Exception:
                        pass
                raise

        gathered = await asyncio.gather(
            *(run_score(criterion) for criterion in CRITERIA),
            return_exceptions=True,
        )
        # Retry only failed primary criteria once. A transient gateway connection
        # failure previously discarded all successful criterion work and tempted
        # callers to retry the entire essay (multiplying cost by four). Keeping
        # the retry here preserves successful results and remains strictly bounded.
        failed_indexes = [
            index
            for index, item in enumerate(gathered)
            if isinstance(item, BaseException)
        ]
        if failed_indexes:
            retried = await asyncio.gather(
                *(run_score(CRITERIA[index]) for index in failed_indexes),
                return_exceptions=True,
            )
            for index, result in zip(failed_indexes, retried, strict=True):
                gathered[index] = result
        failures = [item for item in gathered if isinstance(item, BaseException)]
        if failures:
            raise EvaluationFailed(
                f"{len(failures)} of 4 writing score agents failed: {failures[0]}"
            ) from failures[0]

        scores = {
            execution.criterion: execution
            for execution in gathered
            if isinstance(execution, ScoreExecution)
        }

        # Ensemble is budgeted per essay, not independently per agent. IELTS
        # scorers frequently describe a decision as borderline; letting every
        # criterion self-elect for a second/third call turned "selective" review
        # into the expensive default. Review only the least-certain criterion(s)
        # up to the configured cap. The primary result remains usable if this
        # optional review fails.
        confidence_order = {"low": 0, "medium": 1, "high": 2}
        candidates = sorted(
            (
                score
                for score in scores.values()
                if score.decision.confidence == "low" or score.decision.borderline
            ),
            key=lambda score: (
                confidence_order[score.decision.confidence],
                not score.decision.borderline,
                CRITERIA.index(score.criterion),
            ),
        )
        ensemble_limit = getattr(self.runner, "max_ensemble_criteria", 1)
        for primary in candidates[:ensemble_limit]:
            review_span = _span(
                trace,
                primary.criterion,
                from_cache=False,
                model=self.runner.model,
            )
            try:
                reviewed = await self.runner.score(
                    primary.criterion,
                    essay,
                    exam_type,
                    task_number=task_number,
                    user_id=user_id,
                    chart_context=chart_context,
                    task_prompt=task_prompt,
                    allow_ensemble=True,
                    primary_execution=primary,
                )
                scores[primary.criterion] = reviewed
                _end_score_span(review_span, reviewed, previous=primary)
            except Exception as exc:
                if review_span is not None:
                    try:
                        review_span.update(
                            level="WARNING",
                            status_message=(
                                "Optional ensemble failed; retained primary score: "
                                f"{exc}"
                            ),
                            output={"fallback_band": primary.band_score},
                        )
                        review_span.end()
                    except Exception:
                        pass
        feedback_child = _feedback_span(
            trace, model=self.runner.feedback_model, criteria=list(CRITERIA)
        )
        try:
            feedback = await self.runner.generate_feedback(
                essay,
                scores,
                exam_type,
                task_number=task_number,
                user_id=user_id,
                task_prompt=task_prompt,
            )
            _end_feedback_span(feedback_child, feedback)
        except Exception as exc:
            if feedback_child is not None:
                try:
                    feedback_child.update(
                        level="ERROR",
                        status_message=str(exc),
                        output={"error": str(exc)},
                    )
                    feedback_child.end()
                except Exception:
                    pass
            raise EvaluationFailed(f"Writing feedback agent failed: {exc}") from exc

        evaluations = []
        for criterion in CRITERIA:
            result = self.runner.build_evaluation(
                essay, scores[criterion], feedback.evaluations[criterion]
            )
            evaluations.append(result)
            AGENT_BAND_SCORE.labels(criterion=criterion).observe(result.band_score)
            await _notify(on_partial, result)

        score_executions = [scores[criterion] for criterion in CRITERIA]
        return EvaluationSummary(
            evaluations=evaluations,
            overall_band=calculate_overall_band(
                [result.band_score for result in evaluations]
            ),
            total_tokens=sum(
                item.prompt_tokens + item.completion_tokens
                for item in score_executions
            )
            + feedback.prompt_tokens
            + feedback.completion_tokens,
            total_cost_usd=sum(item.cost_usd or 0.0 for item in score_executions)
            + (feedback.cost_usd or 0.0),
        )

    async def replay_cached(
        self,
        evaluations: list[CriterionEvaluation],
        *,
        trace: Any = None,
        on_partial: PartialCallback | None = None,
    ) -> EvaluationSummary:
        by_criterion = {result.criterion: result for result in evaluations}

        async def replay_one(criterion: Criterion) -> AgentExecution:
            result = by_criterion[criterion]
            execution = AgentExecution(result, 0, 0, 0.0, 0.0)
            child_span = _span(
                trace,
                criterion,
                from_cache=True,
                model=self.runner.model,
            )
            AGENT_BAND_SCORE.labels(criterion=criterion).observe(result.band_score)
            _end_span(child_span, execution, from_cache=True)
            await _notify(on_partial, result)
            return execution

        executions = await asyncio.gather(*(replay_one(item) for item in CRITERIA))
        results = [item.result for item in executions]
        return EvaluationSummary(
            evaluations=results,
            overall_band=calculate_overall_band([item.band_score for item in results]),
            total_tokens=0,
            total_cost_usd=0.0,
        )
        
    async def evaluate_exam_task(
        self,
        essay_text: str,
        exam_type: str,
        *,
        task_number: TaskNumber,
        user_id: str = "anonymous",
        stimulus_s3_key: str | None = None,
        task_prompt: str | None = None,
        trace: Any = None,
        on_partial: PartialCallback | None = None,
        input_source: InputSource = "typed",
    ) -> EvaluationSummary:
        is_academic_task1 = exam_type.lower() == "academic" and task_number == 1

        # TODO(GOA-058 follow-up): when the stimulus-image pipeline lands
        # (ingestion -> S3 -> pre-signing -> exposed on the session API),
        # restore the hard requirement that Academic Task 1 carries an image:
        #     if is_academic_task1 and not stimulus_s3_key:
        #         raise EvaluationFailed("Academic Task 1 requires a stimulus image.")
        #
        # It is removed for now because image-based evaluation is postponed: no
        # ingested question carries an image key, so the guard rejected *every*
        # real Academic Task 1 submission with a 502 — it made the most common
        # writing exam impossible to sit. Evaluating without chart context is a
        # known, accepted limitation until that work lands (Task Response
        # scoring for Academic Task 1 is necessarily weaker without the chart).
        #
        # The optional plumbing below is deliberately kept so re-enabling this
        # needs no structural change: pass a key and chart context flows again.
        chart_context: str | None = None
        if is_academic_task1 and stimulus_s3_key:
            chart_context = await extract_chart_context(stimulus_s3_key, trace=trace)

        if hasattr(self.runner, "score") and hasattr(self.runner, "generate_feedback"):
            return await self._evaluate_staged(
                essay_text,
                exam_type,
                task_number=task_number,
                user_id=user_id,
                trace=trace,
                on_partial=on_partial,
                input_source=input_source,
                chart_context=chart_context,
                task_prompt=task_prompt,
            )

        async def run_one(criterion: Criterion) -> AgentExecution:
            child_span = _span(
                trace,
                criterion,
                from_cache=False,
                model=self.runner.model,
            )
            try:
                execution = await self.runner.evaluate_exam_task(
                    criterion,
                    essay_text,
                    exam_type,
                    task_number,
                    user_id=user_id,
                    chart_context=chart_context,
                    task_prompt=task_prompt,
                )
                AGENT_BAND_SCORE.labels(criterion=criterion).observe(
                    execution.result.band_score
                )
                _end_span(child_span, execution, from_cache=False)
                await _notify(on_partial, execution.result)
                return execution
            except Exception as exc:
                if child_span is not None:
                    try:
                        child_span.update(
                            level="ERROR",
                            status_message=str(exc),
                            output={"error": str(exc)},
                        )
                        child_span.end()
                    except Exception:
                        pass
                raise

        gathered = await asyncio.gather(
            *(run_one(criterion) for criterion in CRITERIA),
            return_exceptions=True,
        )
        failures = [item for item in gathered if isinstance(item, BaseException)]
        if failures:
            raise EvaluationFailed(
                f"{len(failures)} of 4 writing agents failed: {failures[0]}"
            ) from failures[0]

        executions = [item for item in gathered if isinstance(item, AgentExecution)]
        by_criterion = {item.result.criterion: item for item in executions}
        ordered = [by_criterion[criterion] for criterion in CRITERIA]
        evaluations = [item.result for item in ordered]
        return EvaluationSummary(
            evaluations=evaluations,
            overall_band=calculate_overall_band(
                [result.band_score for result in evaluations]
            ),
            total_tokens=sum(
                item.prompt_tokens + item.completion_tokens for item in ordered
            ),
            total_cost_usd=sum(item.cost_usd or 0.0 for item in ordered),
        )


@lru_cache
def get_evaluation_coordinator() -> EvaluationCoordinator:
    return EvaluationCoordinator(get_agent_runner())
