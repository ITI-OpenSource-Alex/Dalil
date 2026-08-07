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
	// FirstTokenMs is time-to-first-token, distinct from LatencyMs (total
	// completion). llm.CompletionResult has always measured it; nothing carried
	// it up, so goa_speaking_llm_first_token_ms was fed LatencyMs and reported
	// something other than what its name claims (GOA-032).
	FirstTokenMs int64 `json:"first_token_ms"`
	TimedOut     bool  `json:"timed_out"`
	// Error is a short breadcrumb for a criterion that did not complete. Empty
	// on success. It exists because "unavailable" alone cannot distinguish a
	// dead credential from a slow provider, and that distinction is the whole
	// point of the instrumentation this ticket adds.
	//
	// json:"-" deliberately: this is for logs and metrics, not for the wire.
	// Dimensions is serialised wholesale into the evaluation frame AND into the
	// persisted evaluation JSONB, so a tagged field would ship raw provider
	// error text to every browser and store it forever.
	Error string `json:"-"`
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
	// Parse JSON output.
	//
	// Band is a *pointer* so that an absent key is distinguishable from a genuine
	// score of zero. With a plain float64, json.Unmarshal SUCCEEDS when "band" is
	// missing and leaves the Go zero value behind — so a response the model never
	// scored was reported as band 0.0 with TimedOut false, i.e. as a completed
	// evaluation. Observed live: articulate native English scored Lexical Resource
	// 0.0 while Fluency and Grammar returned 4 and 5, dragging the overall band from
	// ~4.5 down to 3.5 (BUG-055).
	//
	// band_score is accepted as an alias because that is the key the writing
	// service's agents use, and the model drifts toward it. Accepting the alias is
	// robustness; accepting *neither* silently is the bug.
	var parsed struct {
		Band      *float64 `json:"band"`
		BandScore *float64 `json:"band_score"`
		Feedback  string   `json:"feedback"`
		Examples  []string `json:"examples"`
	}
	err = json.Unmarshal([]byte(cleanedText), &parsed)
	if err != nil {
		return AgentResult{}, fmt.Errorf("failed to parse JSON from LLM: %w (raw response: %s)", err, res.Text)
	}

	scored := parsed.Band
	if scored == nil {
		scored = parsed.BandScore
	}
	if scored == nil {
		// Returning an error is what makes this safe: the swarm marks the criterion
		// unavailable and EXCLUDES it from the overall average, exactly as it does
		// for a timeout. Defaulting to 0.0 would instead average a fabricated score
		// into the candidate's band.
		return AgentResult{}, fmt.Errorf(
			"LLM response for %q contained no band score (looked for \"band\" and \"band_score\"); raw response: %s",
			criterion, res.Text,
		)
	}

	// Bound safety: ensure band is within 0.0 - 9.0
	band := *scored
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
		FirstTokenMs:     res.FirstTokenMs,
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
