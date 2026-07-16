package agents

import (
	"context"
	"errors"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

func TestHolisticCriterion_Success(t *testing.T) {
	mockResponse := `{"band": 7.5, "overall_feedback": "Excellent lexical variety.", "part_notes": {"part1": "Good flow", "part2": "Clear structure", "part3": "Strong arguments"}, "examples": [{"part": 2, "quote": "highly beneficial", "issue": "great collocations"}], "improvement_tip": "Keep reading."}`
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text:             mockResponse,
			PromptTokens:     100,
			CompletionTokens: 50,
			LatencyMs:        1200,
			FirstTokenMs:     200,
		},
	}

	res, err := evaluateHolisticCriterion(context.Background(), mockClient, "Lexical Resource", HolisticLexicalSystemPrompt, "Part 1: Hello...")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if res.Band != 7.5 {
		t.Errorf("expected band 7.5, got %v", res.Band)
	}
	if res.OverallFeedback != "Excellent lexical variety." {
		t.Errorf("expected overall_feedback 'Excellent lexical variety.', got '%s'", res.OverallFeedback)
	}
	if len(res.PartNotes) != 3 || res.PartNotes["part1"] != "Good flow" {
		t.Errorf("part_notes parsed incorrectly: %v", res.PartNotes)
	}
	if len(res.Examples) != 1 || res.Examples[0].Part != 2 || res.Examples[0].Quote != "highly beneficial" || res.Examples[0].Issue != "great collocations" {
		t.Errorf("examples parsed incorrectly: %v", res.Examples)
	}
	if res.ImprovementTip != "Keep reading." {
		t.Errorf("improvement_tip parsed incorrectly: %s", res.ImprovementTip)
	}
}

func TestHolisticCriterion_MarkdownWrapper(t *testing.T) {
	mockResponse := "```json\n{\"band\": 8.0, \"overall_feedback\": \"Good flow.\", \"part_notes\": {}, \"examples\": [], \"improvement_tip\": \"\"}\n```"
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: mockResponse,
		},
	}

	res, err := evaluateHolisticCriterion(context.Background(), mockClient, "Fluency", HolisticFluencySystemPrompt, "Part 1: Hello...")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if res.Band != 8.0 {
		t.Errorf("expected band 8.0 after markdown stripping, got %v", res.Band)
	}
}

func TestHolisticCriterion_BoundsSafety(t *testing.T) {
	mockClientHigh := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": 10.5, "overall_feedback": "Perfect.", "part_notes": {}, "examples": [], "improvement_tip": ""}`,
		},
	}
	resHigh, err := evaluateHolisticCriterion(context.Background(), mockClientHigh, "Grammar", HolisticGrammarSystemPrompt, "Transcript")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if resHigh.Band != 9.0 {
		t.Errorf("expected score capped to 9.0, got %v", resHigh.Band)
	}

	mockClientLow := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": -2.0, "overall_feedback": "Off topic.", "part_notes": {}, "examples": [], "improvement_tip": ""}`,
		},
	}
	resLow, err := evaluateHolisticCriterion(context.Background(), mockClientLow, "Grammar", HolisticGrammarSystemPrompt, "Transcript")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if resLow.Band != 0.0 {
		t.Errorf("expected score capped to 0.0, got %v", resLow.Band)
	}
}

func TestHolisticCriterion_InvalidJSON(t *testing.T) {
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: "{invalid json response}",
		},
	}

	_, err := evaluateHolisticCriterion(context.Background(), mockClient, "Pronunciation", HolisticPronunciationSystemPrompt, "Transcript")
	if err == nil {
		t.Fatal("expected error on parsing invalid JSON, got nil")
	}
}

func TestHolisticCriterion_APIError(t *testing.T) {
	mockClient := &MockLLMClient{
		Err: errors.New("API Rate Limit Exceeded"),
	}

	_, err := evaluateHolisticCriterion(context.Background(), mockClient, "Fluency", HolisticFluencySystemPrompt, "Transcript")
	if err == nil {
		t.Fatal("expected error on stream API failure, got nil")
	}
}
