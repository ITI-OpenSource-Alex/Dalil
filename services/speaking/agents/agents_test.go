package agents

import (
	"context"
	"errors"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

// MockLLMClient is our simple mock that satisfies the LLMClient interface
type MockLLMClient struct {
	Result llm.CompletionResult
	Err    error
}

func (m *MockLLMClient) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	if m.Err != nil {
		return llm.CompletionResult{}, m.Err
	}
	return m.Result, nil
}

func TestEvaluateCriterion_Success(t *testing.T) {
	mockResponse := `{"band": 7.5, "feedback": "Excellent lexical variety.", "examples": ["highly beneficial", "profound effect"]}`
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text:             mockResponse,
			PromptTokens:     100,
			CompletionTokens: 50,
			LatencyMs:        1200,
			FirstTokenMs:     200,
		},
	}

	res, err := EvaluateLexical(context.Background(), mockClient, "Describe a hobby.", "IELTS Part 2", "I enjoy playing tennis...")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if res.Band != 7.5 {
		t.Errorf("expected band 7.5, got %v", res.Band)
	}
	if res.Feedback != "Excellent lexical variety." {
		t.Errorf("expected feedback 'Excellent lexical variety.', got '%s'", res.Feedback)
	}
	if len(res.Examples) != 2 || res.Examples[0] != "highly beneficial" {
		t.Errorf("examples parsed incorrectly: %v", res.Examples)
	}
	if res.PromptTokens != 100 || res.CompletionTokens != 50 || res.LatencyMs != 1200 {
		t.Errorf("metrics telemetry not propagated correctly")
	}
}

func TestEvaluateCriterion_MarkdownWrapper(t *testing.T) {
	mockResponse := "```json\n{\"band\": 8.0, \"feedback\": \"Good flow.\", \"examples\": []}\n```"
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: mockResponse,
		},
	}

	res, err := EvaluateFluency(context.Background(), mockClient, "Describe a hobby.", "IELTS Part 2", "I enjoy playing tennis...")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if res.Band != 8.0 {
		t.Errorf("expected band 8.0 after markdown stripping, got %v", res.Band)
	}
}

func TestEvaluateCriterion_BoundsSafety(t *testing.T) {
	// Case 1: Band score exceeds 9.0
	mockClientHigh := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": 10.5, "feedback": "Perfect.", "examples": []}`,
		},
	}
	resHigh, err := EvaluateGrammar(context.Background(), mockClientHigh, "Prompt", "Type", "Transcript")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if resHigh.Band != 9.0 {
		t.Errorf("expected score capped to 9.0, got %v", resHigh.Band)
	}

	// Case 2: Band score falls below 0.0
	mockClientLow := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": -2.0, "feedback": "Off topic.", "examples": []}`,
		},
	}
	resLow, err := EvaluateGrammar(context.Background(), mockClientLow, "Prompt", "Type", "Transcript")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if resLow.Band != 0.0 {
		t.Errorf("expected score capped to 0.0, got %v", resLow.Band)
	}
}

func TestEvaluateCriterion_InvalidJSON(t *testing.T) {
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: "{invalid json response}",
		},
	}

	_, err := EvaluatePronunciation(context.Background(), mockClient, "Prompt", "Type", "Transcript")
	if err == nil {
		t.Fatal("expected error on parsing invalid JSON, got nil")
	}
}

func TestEvaluateCriterion_APIError(t *testing.T) {
	mockClient := &MockLLMClient{
		Err: errors.New("API Rate Limit Exceeded"),
	}

	_, err := EvaluateFluency(context.Background(), mockClient, "Prompt", "Type", "Transcript")
	if err == nil {
		t.Fatal("expected error on stream API failure, got nil")
	}
}

// BUG-055: a missing band key must be an error, never a silent 0.0.
//
// With `Band float64`, json.Unmarshal SUCCEEDS on a response that omits "band"
// and leaves Go's zero value behind, so an unscored criterion was reported as
// band 0.0 with TimedOut false — a completed evaluation carrying a fabricated
// score. Observed live: articulate native English scored Lexical Resource 0.0
// alongside Fluency 4 and Grammar 5, pulling the overall band down to 3.5.
//
// An error is the safe outcome because the swarm excludes errored criteria from
// the overall average, exactly as it excludes timeouts.
func TestEvaluateCriterion_MissingBandIsAnErrorNotZero(t *testing.T) {
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			// Valid JSON, plausible feedback, no band anywhere.
			Text: `{"feedback": "Good range of vocabulary.", "examples": ["nevertheless"]}`,
		},
	}

	res, err := EvaluateLexical(context.Background(), mockClient, "Describe a hobby.", "IELTS Part 2", "I enjoy tennis...")
	if err == nil {
		t.Fatalf("expected an error for a response with no band, got band %v", res.Band)
	}
	if res.Band != 0 || res.TimedOut {
		t.Errorf("a failed parse must not return a usable result, got %+v", res)
	}
}

// A real zero must still be honoured — the point is distinguishing absent from
// zero, not refusing zero.
func TestEvaluateCriterion_ExplicitZeroBandIsAccepted(t *testing.T) {
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": 0.0, "feedback": "No intelligible response.", "examples": []}`,
		},
	}

	res, err := EvaluateLexical(context.Background(), mockClient, "Describe a hobby.", "IELTS Part 2", "...")
	if err != nil {
		t.Fatalf("an explicit band of 0 is a legitimate score, got error %v", err)
	}
	if res.Band != 0.0 {
		t.Errorf("expected band 0.0, got %v", res.Band)
	}
}

// band_score is the key the writing service's agents use; the model drifts
// toward it. Accepting the alias is robustness — accepting neither silently was
// the bug.
func TestEvaluateCriterion_AcceptsBandScoreAlias(t *testing.T) {
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band_score": 6.5, "feedback": "Adequate range.", "examples": []}`,
		},
	}

	res, err := EvaluateLexical(context.Background(), mockClient, "Describe a hobby.", "IELTS Part 2", "I enjoy tennis...")
	if err != nil {
		t.Fatalf("expected band_score to be accepted, got error %v", err)
	}
	if res.Band != 6.5 {
		t.Errorf("expected band 6.5 from band_score alias, got %v", res.Band)
	}
}
