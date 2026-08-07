import pytest
import base64
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents import extract_chart_context
from app.evaluation import EvaluationCoordinator, EvaluationFailed

@pytest.fixture
def mock_fetch_bytes():
    with patch("app.agents._fetch_chart_bytes", new_callable=AsyncMock) as m:
        # Mocking a tiny fake valid PNG image to satisfy detection
        m.return_value = b"\x89PNG\r\n\x1a\n" + b"fake_image_data"
        yield m

@pytest.fixture
def mock_anthropic():
    with patch("anthropic.AsyncAnthropic") as mock_cls:
        client_instance = MagicMock()
        mock_cls.return_value = client_instance
        # Mock the create response
        response_mock = MagicMock()
        response_mock.content = [MagicMock(text="A chart showing data.")]
        client_instance.messages.create = AsyncMock(return_value=response_mock)
        yield client_instance

@pytest.mark.asyncio
async def test_extraction_schema_unchanged(mock_fetch_bytes, mock_anthropic):
    # test_extraction_schema_unchanged — snapshot-assert the output schema against the pre-change shape.
    result = await extract_chart_context("fake/s3/key")
    assert isinstance(result, str)
    assert result == "A chart showing data."
    
    # Assert that claude-opus-4-8 is used and the payload is correct
    mock_anthropic.messages.create.assert_called_once()
    kwargs = mock_anthropic.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-8"
    messages = kwargs["messages"]
    assert len(messages) == 1
    content = messages[0]["content"]
    # Should contain exactly an image block and a text block
    assert len(content) == 2
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[1]["type"] == "text"


class _FakeTrace:
    """Minimal stand-in for a Langfuse observation handle."""

    def __init__(self) -> None:
        self.observations: list[dict] = []

    def start_observation(self, **kwargs):
        record = {"kwargs": kwargs, "updates": [], "ended": False}
        self.observations.append(record)

        class _Span:
            def update(_self, **update_kwargs):
                record["updates"].append(update_kwargs)

            def end(_self):
                record["ended"] = True

        return _Span()


def _vision_observations(trace: _FakeTrace) -> list[dict]:
    return [
        o for o in trace.observations
        if o["kwargs"].get("name") == "writing-vision-stimulus"
    ]


@pytest.mark.asyncio
async def test_vision_call_emits_langfuse_generation_span(
    mock_fetch_bytes, mock_anthropic
):
    trace = _FakeTrace()

    result = await extract_chart_context("fake/s3/key", trace=trace)

    assert result == "A chart showing data."
    vision = _vision_observations(trace)
    assert len(vision) == 1
    kwargs = vision[0]["kwargs"]
    assert kwargs["as_type"] == "generation"
    assert kwargs["model"] == "claude-opus-4-8"
    assert kwargs["input"]["s3_key"] == "fake/s3/key"
    assert kwargs["input"]["media_type"] == "image/png"
    assert vision[0]["ended"] is True
    assert vision[0]["updates"][0]["output"] == "A chart showing data."


@pytest.mark.asyncio
async def test_vision_span_records_error_and_reraises(mock_fetch_bytes, mock_anthropic):
    trace = _FakeTrace()
    mock_anthropic.messages.create.side_effect = RuntimeError("gateway 503")

    with pytest.raises(RuntimeError, match="gateway 503"):
        await extract_chart_context("fake/s3/key", trace=trace)

    vision = _vision_observations(trace)
    assert len(vision) == 1
    assert vision[0]["updates"][0]["level"] == "ERROR"
    assert vision[0]["ended"] is True


@pytest.mark.asyncio
async def test_vision_call_without_trace_is_untraced_but_succeeds(
    mock_fetch_bytes, mock_anthropic
):
    # A missing Langfuse client must never break evaluation.
    assert await extract_chart_context("fake/s3/key") == "A chart showing data."


@pytest.mark.asyncio
async def test_academic_task1_sends_image_block(mock_fetch_bytes, mock_anthropic):
    from app.evaluation import get_evaluation_coordinator
    coordinator = get_evaluation_coordinator()
    
    with patch.object(coordinator.runner, "evaluate_exam_task", new_callable=AsyncMock) as mock_eval:
        from app.schemas import CriterionEvaluation
        from app.agents import AgentExecution
        def mock_side_effect(criterion, *args, **kwargs):
            return AgentExecution(
                result=CriterionEvaluation(
                    criterion=criterion,
                    band_score=7.0,
                    feedback="Good",
                    improvement_tip="Tip",
                    word_count=200,
                    inline_issues=[]
                ),
                prompt_tokens=10,
                completion_tokens=10,
                latency_ms=10.0,
                cost_usd=0.01
            )
        mock_eval.side_effect = mock_side_effect
        
        await coordinator.evaluate_exam_task(
            essay_text="test",
            exam_type="Academic",
            task_number=1,
            stimulus_s3_key="some/s3/key.png"
        )
        mock_fetch_bytes.assert_called_once_with("some/s3/key.png")
        mock_anthropic.messages.create.assert_called_once()
        mock_eval.assert_called()
        assert mock_eval.call_args.kwargs.get("chart_context") == "A chart showing data."

@pytest.mark.asyncio
async def test_general_task1_sends_no_image_block(mock_fetch_bytes, mock_anthropic):
    from app.evaluation import get_evaluation_coordinator
    coordinator = get_evaluation_coordinator()
    
    with patch.object(coordinator.runner, "evaluate_exam_task", new_callable=AsyncMock) as mock_eval:
        from app.schemas import CriterionEvaluation
        from app.agents import AgentExecution
        def mock_side_effect(criterion, *args, **kwargs):
            return AgentExecution(
                result=CriterionEvaluation(
                    criterion=criterion,
                    band_score=7.0,
                    feedback="Good",
                    improvement_tip="Tip",
                    word_count=200,
                    inline_issues=[]
                ),
                prompt_tokens=10,
                completion_tokens=10,
                latency_ms=10.0,
                cost_usd=0.01
            )
        mock_eval.side_effect = mock_side_effect
        
        await coordinator.evaluate_exam_task(
            essay_text="test",
            exam_type="General",
            task_number=1,
            stimulus_s3_key="some/s3/key.png"
        )
        mock_fetch_bytes.assert_not_called()
        mock_anthropic.messages.create.assert_not_called()
        mock_eval.assert_called()
        assert mock_eval.call_args.kwargs.get("chart_context") is None

@pytest.mark.asyncio
async def test_task2_sends_no_image_block(mock_fetch_bytes, mock_anthropic):
    from app.evaluation import get_evaluation_coordinator
    coordinator = get_evaluation_coordinator()
    
    with patch.object(coordinator.runner, "evaluate_exam_task", new_callable=AsyncMock) as mock_eval:
        from app.schemas import CriterionEvaluation
        from app.agents import AgentExecution
        def mock_side_effect(criterion, *args, **kwargs):
            return AgentExecution(
                result=CriterionEvaluation(
                    criterion=criterion,
                    band_score=7.0,
                    feedback="Good",
                    improvement_tip="Tip",
                    word_count=200,
                    inline_issues=[]
                ),
                prompt_tokens=10,
                completion_tokens=10,
                latency_ms=10.0,
                cost_usd=0.01
            )
        mock_eval.side_effect = mock_side_effect
        
        await coordinator.evaluate_exam_task(
            essay_text="test",
            exam_type="Academic",
            task_number=2,
            stimulus_s3_key="some/s3/key.png"
        )
        mock_fetch_bytes.assert_not_called()
        mock_anthropic.messages.create.assert_not_called()
        mock_eval.assert_called()
        assert mock_eval.call_args.kwargs.get("chart_context") is None

@pytest.mark.asyncio
async def test_academic_task1_without_image_evaluates_without_chart_context(
    mock_fetch_bytes, mock_anthropic
):
    """
    Image-based evaluation is postponed, so Academic Task 1 with no stimulus
    key must EVALUATE rather than fail.

    This test previously asserted the opposite — that it raised
    EvaluationFailed("Academic Task 1 requires a stimulus image"). That guard
    was correct only while the stimulus pipeline was expected to exist. In
    practice no ingested question carries an image key, so the guard rejected
    every real Academic Task 1 submission with a 502 and made the most common
    writing exam impossible to sit.

    TODO(GOA-058 follow-up): when the stimulus pipeline lands, restore the
    guard in app/evaluation.py and flip this test back to expecting
    EvaluationFailed.
    """
    from app.evaluation import get_evaluation_coordinator
    coordinator = get_evaluation_coordinator()

    with patch.object(coordinator.runner, "evaluate_exam_task", new_callable=AsyncMock) as mock_eval:
        from app.schemas import CriterionEvaluation
        from app.agents import AgentExecution

        def mock_side_effect(criterion, *args, **kwargs):
            return AgentExecution(
                result=CriterionEvaluation(
                    criterion=criterion,
                    band_score=7.0,
                    feedback="Good",
                    improvement_tip="Tip",
                    word_count=200,
                    inline_issues=[]
                ),
                prompt_tokens=10,
                completion_tokens=10,
                latency_ms=10.0,
                cost_usd=0.01
            )
        mock_eval.side_effect = mock_side_effect

        summary = await coordinator.evaluate_exam_task(
            essay_text="test",
            exam_type="Academic",
            task_number=1,
            stimulus_s3_key=None
        )

    # It evaluated all four criteria and produced a band.
    assert len(summary.evaluations) == 4
    assert summary.overall_band == 7.0

    # No image was fetched and no vision call was made.
    mock_fetch_bytes.assert_not_called()
    mock_anthropic.messages.create.assert_not_called()

    # The agents ran without chart context — the accepted limitation.
    assert mock_eval.call_args.kwargs.get("chart_context") is None


@pytest.mark.asyncio
async def test_vision_span_is_attached_to_the_evaluation_trace(
    mock_fetch_bytes, mock_anthropic
):
    """GOA-093 AC: Langfuse traces the Claude Vision call.

    The vision generation must hang off the same trace as the four criterion
    agents, not float unattached.
    """
    from app.evaluation import get_evaluation_coordinator
    coordinator = get_evaluation_coordinator()
    trace = _FakeTrace()

    with patch.object(coordinator.runner, "evaluate_exam_task", new_callable=AsyncMock) as mock_eval:
        from app.agents import AgentExecution
        from app.schemas import CriterionEvaluation

        def mock_side_effect(criterion, *args, **kwargs):
            return AgentExecution(
                result=CriterionEvaluation(
                    criterion=criterion,
                    band_score=7.0,
                    feedback="Good",
                    improvement_tip="Tip",
                    word_count=200,
                    inline_issues=[]
                ),
                prompt_tokens=10,
                completion_tokens=10,
                latency_ms=10.0,
                cost_usd=0.01
            )
        mock_eval.side_effect = mock_side_effect

        await coordinator.evaluate_exam_task(
            essay_text="test",
            exam_type="Academic",
            task_number=1,
            stimulus_s3_key="some/s3/key.png",
            trace=trace,
        )

    vision = _vision_observations(trace)
    assert len(vision) == 1
    assert vision[0]["kwargs"]["model"] == "claude-opus-4-8"
    # Four criterion spans plus the one vision span, all on the same trace.
    assert len(trace.observations) == 5
