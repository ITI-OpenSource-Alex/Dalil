package agents

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
	"strings"
)

// AgentResult represents the output metrics and feedback for a single IELTS criterion

type AgentResult struct {
	Criterion        string   `json:"criterion"`
	Band             float64  `json:"band"`
	Feedback         string   `json:"feedback"`
	Examples         []string `json:"examples"`
	PromptTokens     int      `json:"prompt_tokens"`
	CompletionTokens int      `json:"completion_tokens"`
	LatencyMs        int64    `json:"latency_ms"`
	TimedOut         bool     `json:"timed_out"`
}

// LLMClient abstracts our Anthropic wrapper to enable offline unit testing

type LLMClient interface {
	StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error)
}

// evaluateCriterion manages prompt construction, completion execution, and parsing/bound safety
func cleanJSONResponse(raw string) string {
	cleanedText := strings.TrimSpace(raw)
	if strings.HasPrefix(cleanedText, "```json") {
		cleanedText = strings.TrimPrefix(cleanedText, "```json")
		cleanedText = strings.TrimSuffix(cleanedText, "```")
		cleanedText = strings.TrimSpace(cleanedText)
	} else if strings.HasPrefix(cleanedText, "```") {
		cleanedText = strings.TrimPrefix(cleanedText, "```")
		cleanedText = strings.TrimSuffix(cleanedText, "```")
		cleanedText = strings.TrimSpace(cleanedText)
	}
	return cleanedText
}

func evaluateCriterion(ctx context.Context, client LLMClient, criterion, systemPrompt, questionPrompt, questionType, transcript string) (AgentResult, error) {
	// Build prompt containing prompt context and transcript
	userPrompt := fmt.Sprintf("Question Prompt: %s\nQuestion Type: %s\nCandidate Transcript: %s", questionPrompt, questionType, transcript)
	res, err := client.StreamCompletion(ctx, systemPrompt, userPrompt)
	if err != nil {
		return AgentResult{}, err
	}
	// Scrub potential markdown wrappers
	cleanedText := cleanJSONResponse(res.Text)
	// Parse JSON output
	var parsed struct {
		Band     float64  `json:"band"`
		Feedback string   `json:"feedback"`
		Examples []string `json:"examples"`
	}
	err = json.Unmarshal([]byte(cleanedText), &parsed)
	if err != nil {
		return AgentResult{}, fmt.Errorf("failed to parse JSON from LLM: %w (raw response: %s)", err, res.Text)
	}
	// Bound safety: ensure band is within 0.0 - 9.0
	band := parsed.Band
	if band < 0.0 {
		band = 0.0
	} else if band > 9.0 {
		band = 9.0
	}
	return AgentResult{
		Criterion:        criterion,
		Band:             band,
		Feedback:         parsed.Feedback,
		Examples:         parsed.Examples,
		PromptTokens:     res.PromptTokens,
		CompletionTokens: res.CompletionTokens,
		LatencyMs:        res.LatencyMs,
		TimedOut:         false,
	}, nil
}

// EvaluateFluency evaluates Fluency and Coherence
func EvaluateFluency(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string) (AgentResult, error) {
	return evaluateCriterion(ctx, client, "Fluency and Coherence", FluencySystemPrompt, questionPrompt, questionType, transcript)
}

// EvaluateLexical evaluates Lexical Resource
func EvaluateLexical(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string) (AgentResult, error) {
	return evaluateCriterion(ctx, client, "Lexical Resource", LexicalSystemPrompt, questionPrompt, questionType, transcript)
}

// EvaluateGrammar evaluates Grammatical Range and Accuracy
func EvaluateGrammar(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string) (AgentResult, error) {
	return evaluateCriterion(ctx, client, "Grammatical Range and Accuracy", GrammarSystemPrompt, questionPrompt, questionType, transcript)
}

// EvaluatePronunciation evaluates Pronunciation
func EvaluatePronunciation(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string) (AgentResult, error) {
	return evaluateCriterion(ctx, client, "Pronunciation", PronunciationSystemPrompt, questionPrompt, questionType, transcript)
}
