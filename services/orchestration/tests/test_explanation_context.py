import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest


def valid_payload():
    return {
        "userId": "student-1",
        "sessionId": "session-1",
        "message": "Why did I receive this score?",
        "explanationContext": {
            "kind": "writing_score",
            "title": "Writing criterion band 6.0",
            "subjectId": "exam-1:task-2",
            "facts": [
                {
                    "label": "Grammar band",
                    "value": "6.0",
                }
            ],
            "limitations": ["This is a practice estimate."],
        },
    }


def test_explanation_context_accepts_bounded_typed_evidence():
    request = ChatRequest.model_validate(valid_payload())

    assert request.explanationContext is not None
    assert request.explanationContext.kind == "writing_score"
    assert request.explanationContext.facts[0].label == "Grammar band"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda context: context.update(kind="unknown_kind"),
        lambda context: context.update(facts=[]),
        lambda context: context.update(
            facts=[{"label": f"Fact {index}", "value": "x"} for index in range(25)]
        ),
        lambda context: context.update(limitations=["x" * 501]),
    ],
)
def test_explanation_context_rejects_unbounded_or_unknown_evidence(mutation):
    payload = valid_payload()
    mutation(payload["explanationContext"])

    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)
