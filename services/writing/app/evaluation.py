import asyncio
import inspect
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from typing import Any, Awaitable, Callable

from app.agents import CRITERIA, AgentExecution, Criterion, WritingAgentRunner, get_agent_runner
from app.metrics import AGENT_BAND_SCORE
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
    ) -> EvaluationSummary:
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
            total_cost_usd=sum(item.cost_usd for item in ordered),
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
            total_cost_usd=sum(item.cost_usd for item in ordered),
        )


@lru_cache
def get_evaluation_coordinator() -> EvaluationCoordinator:
    return EvaluationCoordinator(get_agent_runner())
