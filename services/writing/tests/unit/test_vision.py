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
                    highlighted_issues=[]
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
                    highlighted_issues=[]
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
                    highlighted_issues=[]
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
async def test_academic_task1_fails_without_image():
    from app.evaluation import get_evaluation_coordinator
    coordinator = get_evaluation_coordinator()
    
    with pytest.raises(EvaluationFailed, match="Academic Task 1 requires a stimulus image"):
        await coordinator.evaluate_exam_task(
            essay_text="test",
            exam_type="Academic",
            task_number=1,
            stimulus_s3_key=None
        )
