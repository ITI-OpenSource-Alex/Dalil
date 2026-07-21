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
