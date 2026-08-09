package agents

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

// AgentResult represents the output metrics and feedback for a single IELTS criterion

type AgentResult struct {
	Criterion string   `json:"criterion"`
	Band      float64  `json:"band"`
	Feedback  string   `json:"feedback"`
	Examples  []string `json:"examples"`
	// RubricMatches are the official descriptors this band was justified
	// against, already resolved to the frozen rubric. Empty when the model cited
	// nothing resolvable -- a citation the code could not verify is not shown.
	RubricMatches    []contract.RubricMatch `json:"rubric_matches,omitempty"`
	PromptTokens     int                    `json:"prompt_tokens"`
	CompletionTokens int                    `json:"completion_tokens"`
	LatencyMs        int64                  `json:"latency_ms"`
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

func evaluateCriterion(ctx context.Context, client LLMClient, criterion, systemPrompt, questionPrompt, questionType, transcript string, features *ProsodyFeatures) (AgentResult, error) {
	// GOA-133. The measured feature block goes FIRST, ahead of the transcript, and
	// only for the criteria that are defined over acoustics.
	//
	// A nil `features` renders nothing at all. It must never render zeros: a block
	// reading "0 words per minute, 0 pauses" describes a candidate who said
	// nothing, which is a worse lie than an absent block -- the BUG-055 shape
	// applied to prosody.
	//
	// Deliberately not fenced as untrusted input: these are our own computed
	// numbers, and fencing them would tell the model to distrust the one part of
	// the prompt it should trust most. The transcript's fencing is unchanged.
	var prosody string
	if features != nil {
		prosody = features.Render() + "\n"
	}
	userPrompt := fmt.Sprintf("%sQuestion Prompt: %s\nQuestion Type: %s\nCandidate Transcript: %s", prosody, questionPrompt, questionType, transcript)
	// SPEAK-EVAL-003: the prompt is grounded at call time -- the frozen
	// descriptors, with ids, appended to the criterion's own instructions. It is
	// additive: a model that returns no citations scores exactly as before.
	res, err := client.StreamCompletion(ctx, groundedPromptFor(systemPrompt, criterion), userPrompt)
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
		// Optional, and not believed until parseRubricMatches resolves each id
		// against the frozen rubric.
		RubricMatches []rawRubricMatch `json:"rubric_matches"`
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
		RubricMatches:    parseRubricMatches(parsed.RubricMatches, canonicalCriterionID[criterion]),
		PromptTokens:     res.PromptTokens,
		CompletionTokens: res.CompletionTokens,
		LatencyMs:        res.LatencyMs,
		FirstTokenMs:     res.FirstTokenMs,
		TimedOut:         false,
	}, nil
}

// EvaluateFluency evaluates Fluency and Coherence
func EvaluateFluency(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string, features *ProsodyFeatures) (AgentResult, error) {
	return evaluateCriterion(ctx, client, "Fluency and Coherence", FluencySystemPrompt, questionPrompt, questionType, transcript, features)
}

// EvaluateLexical evaluates Lexical Resource
func EvaluateLexical(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string, features *ProsodyFeatures) (AgentResult, error) {
	// nil: this criterion has no use for prosody and the block is pure token cost.
	return evaluateCriterion(ctx, client, "Lexical Resource", LexicalSystemPrompt, questionPrompt, questionType, transcript, nil)
}

// EvaluateGrammar evaluates Grammatical Range and Accuracy
func EvaluateGrammar(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string, features *ProsodyFeatures) (AgentResult, error) {
	// nil: this criterion has no use for prosody and the block is pure token cost.
	return evaluateCriterion(ctx, client, "Grammatical Range and Accuracy", GrammarSystemPrompt, questionPrompt, questionType, transcript, nil)
}

// EvaluatePronunciation evaluates Pronunciation
func EvaluatePronunciation(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string, features *ProsodyFeatures) (AgentResult, error) {
	// GOA-133 established that this criterion reasons from recognition
	// confidence and pause structure. With no measured features there is no
	// evidence for it to reason from, so it declines rather than guessing from
	// the wording of the transcript -- which carries no acoustic information at
	// all.
	//
	// Declining costs the caller one criterion and leaves three, which still
	// clears MinCriteriaForOverallBand. Guessing cost a band 8 candidate 2.5
	// bands (SPEAK-EVAL-007).
	if features == nil {
		return AgentResult{}, errors.New(AgentErrorInsufficientEvidence)
	}
	return evaluateCriterion(ctx, client, "Pronunciation", PronunciationSystemPrompt, questionPrompt, questionType, transcript, features)
}
