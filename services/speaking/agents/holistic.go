// agents/holistic.go
package agents

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
)

// TranscriptExample represents a specific quote from a part of the exam.
type TranscriptExample struct {
	Part  int    `json:"part"`
	Quote string `json:"quote"`
	Issue string `json:"issue"`
}

// HolisticAgentResult is the extended result from a single criterion's agent.
type HolisticAgentResult struct {
	Criterion       string              `json:"criterion"`
	Band            float64             `json:"band"`
	OverallFeedback string              `json:"overall_feedback"`
	PartNotes       map[string]string   `json:"part_notes"`
	Examples        []TranscriptExample `json:"examples"`
	ImprovementTip  string              `json:"improvement_tip"`
	TimedOut        bool                `json:"timed_out"`
}

// HolisticSwarmResult aggregates the holistic agent results.
type HolisticSwarmResult struct {
	Status          string                         `json:"status"` // "completed" or "failed"
	Partial         bool                           `json:"partial"`
	OverallBand     float64                        `json:"overall_band"`
	Dimensions      map[string]HolisticAgentResult `json:"dimensions"`
	OverallFeedback string                         `json:"overall_feedback"`
}

func evaluateHolisticCriterion(ctx context.Context, client LLMClient, criterion, systemPrompt, concatenatedTranscript string) (HolisticAgentResult, error) {
	// Build prompt. The grading rubric and JSON contract are passed as the system
	// prompt, but the opus-4-8 gateway intermittently drops the system role and
	// falls back to a generic "Claude Code" identity — the model then refuses,
	// replying "I don't have any IELTS grading instructions in my system prompt"
	// as prose, which fails JSON parsing. To survive that, we ALSO inline the
	// full spec into the user turn (which the gateway always honors), so the task
	// is fully specified regardless of whether the system role reaches the model.
	// Never reference "your system prompt" here — when it has been dropped, that
	// phrasing makes the model refuse instead of grade.
	userPrompt := fmt.Sprintf(
		"%s\n\n"+
			"Grade the following IELTS candidate transcript using the rubric and JSON "+
			"schema above. Output ONLY the raw JSON object — no preamble, no "+
			"explanation, no markdown fences. If the transcript is short, still "+
			"return a best-effort band; do not ask for more information.\n\n"+
			"Candidate Transcript (All Parts):\n%s",
		systemPrompt, concatenatedTranscript)
	res, err := client.StreamCompletion(ctx, systemPrompt, userPrompt)
	if err != nil {
		return HolisticAgentResult{}, err
	}

	cleanedText := cleanJSONResponse(res.Text)

	var parsed struct {
		Band            float64             `json:"band"`
		OverallFeedback string              `json:"overall_feedback"`
		PartNotes       map[string]string   `json:"part_notes"`
		Examples        []TranscriptExample `json:"examples"`
		ImprovementTip  string              `json:"improvement_tip"`
	}

	err = json.Unmarshal([]byte(cleanedText), &parsed)
	if err != nil {
		return HolisticAgentResult{}, fmt.Errorf("failed to parse JSON from LLM: %w (raw response: %s)", err, res.Text)
	}

	band := parsed.Band
	if band < 0.0 {
		band = 0.0
	} else if band > 9.0 {
		band = 9.0
	}

	return HolisticAgentResult{
		Criterion:       criterion,
		Band:            band,
		OverallFeedback: parsed.OverallFeedback,
		PartNotes:       parsed.PartNotes,
		Examples:        parsed.Examples,
		ImprovementTip:  parsed.ImprovementTip,
		TimedOut:        false,
	}, nil
}

// attemptTimeout bounds a single criterion's gateway stream. Measured latency
// against the opus-4-8 gateway is highly variable: ~20s at best and ~40s in a
// healthy patch, but the gateway also has slow patches where a call legitimately
// needs 60-100s (most of it the server-side thinking block that streams before
// any answer text). The slowness is correlated in time — when the gateway is
// slow, every concurrent call and any retry hits the same slow moment — so a
// retry against a tight cap does not recover, it just burns another timeout. We
// therefore use a SINGLE attempt with a generous cap. Because all four criteria
// stream concurrently, the cap is also the swarm's worst-case wall-clock, so we
// keep it just under the handler's 120s deadline: 110s absorbs almost the whole
// latency tail while leaving the handler a small margin to encode the response.
// Only a criterion that truly hangs past 110s is abandoned, and it is then
// excluded from the average (see EvaluateHolisticSwarm) so the request still
// returns a valid band from the survivors.
const attemptTimeout = 110 * time.Second

// evaluateHolisticCriterionCapped runs one criterion under a per-call cap
// derived from the parent context. One attempt only — see attemptTimeout for why
// a retry does not help against this gateway's time-correlated latency.
func evaluateHolisticCriterionCapped(ctx context.Context, client LLMClient, criterion, systemPrompt, concatenatedTranscript string) (HolisticAgentResult, error) {
	attemptCtx, cancel := context.WithTimeout(ctx, attemptTimeout)
	defer cancel()
	return evaluateHolisticCriterion(attemptCtx, client, criterion, systemPrompt, concatenatedTranscript)
}

// EvaluateHolisticSwarm orchestrates parallel evaluations for the full exam.
func EvaluateHolisticSwarm(ctx context.Context, client LLMClient, concatenatedTranscript string) (HolisticSwarmResult, error) {
	var wg sync.WaitGroup
	wg.Add(4)

	var mu sync.Mutex
	results := make(map[string]HolisticAgentResult)

	// All four criterion agents stream concurrently. Measured 4-way concurrency
	// against the opus-4-8 gateway completes in ~40s wall-clock (= the slowest
	// single call) with no failures, so there is no need to throttle. An earlier
	// Semaphore(2) here serialized the calls into two waves and pushed the
	// second wave into the deadline — it was masking the old MaxTokens=1024 /
	// thinking-block bug, not a real gateway concurrency limit.

	runAgent := func(criterionName string, systemPrompt string) {
		defer wg.Done()

		resChan := make(chan HolisticAgentResult, 1)
		errChan := make(chan error, 1)

		go func() {
			res, err := evaluateHolisticCriterionCapped(ctx, client, criterionName, systemPrompt, concatenatedTranscript)
			if err != nil {
				errChan <- err
				return
			}
			resChan <- res
		}()

		select {
		case res := <-resChan:
			mu.Lock()
			results[criterionName] = res
			mu.Unlock()
		case err := <-errChan:
			// Surface WHY this criterion failed — malformed LLM JSON, a gateway
			// error response, or a per-call timeout all land here. Without this
			// the criterion silently becomes a band-0 hole in the result.
			log.Error().Err(err).Str("criterion", criterionName).
				Msg("Holistic criterion agent failed")
			mu.Lock()
			results[criterionName] = HolisticAgentResult{
				Criterion:       criterionName,
				Band:            0.0,
				OverallFeedback: "Evaluation unavailable due to an internal error.",
				TimedOut:        true,
			}
			mu.Unlock()
		case <-ctx.Done():
			log.Error().Err(ctx.Err()).Str("criterion", criterionName).
				Msg("Holistic criterion agent hit the swarm deadline")
			mu.Lock()
			results[criterionName] = HolisticAgentResult{
				Criterion:       criterionName,
				Band:            0.0,
				OverallFeedback: "Evaluation unavailable due to response timeout.",
				TimedOut:        true,
			}
			mu.Unlock()
		}
	}

	go runAgent("Fluency and Coherence", HolisticFluencySystemPrompt)
	go runAgent("Lexical Resource", HolisticLexicalSystemPrompt)
	go runAgent("Grammatical Range and Accuracy", HolisticGrammarSystemPrompt)
	go runAgent("Pronunciation", HolisticPronunciationSystemPrompt)

	wg.Wait()

	var totalBand float64
	var completedCount int
	var partial bool

	for _, res := range results {
		if !res.TimedOut {
			totalBand += res.Band
			completedCount++
		} else {
			partial = true
		}
	}

	if completedCount == 0 {
		return HolisticSwarmResult{
			Status:          "failed",
			Partial:         false,
			OverallBand:     0.0,
			Dimensions:      results,
			OverallFeedback: "Evaluation completely failed due to timeouts or internal errors on all criteria.",
		}, fmt.Errorf("all evaluation agents timed out or failed")
	}

	avgBand := totalBand / float64(completedCount)
	overallBand := RoundIELTSBand(avgBand)

	var feedbackLines []string
	for _, name := range []string{"Fluency and Coherence", "Lexical Resource", "Grammatical Range and Accuracy", "Pronunciation"} {
		res := results[name]
		feedbackLines = append(feedbackLines, fmt.Sprintf("- **%s** (Band %.1f): %s", name, res.Band, res.OverallFeedback))
	}
	overallFeedback := "### IELTS Speaking Rubric Evaluation Summary:\n\n" + strings.Join(feedbackLines, "\n")

	return HolisticSwarmResult{
		Status:          "completed",
		Partial:         partial,
		OverallBand:     overallBand,
		Dimensions:      results,
		OverallFeedback: overallFeedback,
	}, nil
}
