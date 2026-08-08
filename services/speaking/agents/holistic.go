// agents/holistic.go
package agents

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
	"github.com/rs/zerolog/log"
)

// TranscriptExample represents a specific quote from a part of the exam.
type TranscriptExample struct {
	Part  int    `json:"part"`
	Quote string `json:"quote"`
	Issue string `json:"issue"`
}

// HolisticAgentResult is the extended result from a single criterion's agent.
//
// KEEP IN SYNC WITH AgentResult in swarm.go. The two describe the same thing for
// two execution paths, and GOA-134 exists because they drifted: this one had no
// Error field and no way to distinguish a provider failure from a deadline.
type HolisticAgentResult struct {
	Criterion       string              `json:"criterion"`
	Band            float64             `json:"band"`
	OverallFeedback string              `json:"overall_feedback"`
	PartNotes       map[string]string   `json:"part_notes"`
	Examples        []TranscriptExample `json:"examples"`
	ImprovementTip  string              `json:"improvement_tip"`
	// RubricMatches mirrors AgentResult.RubricMatches: descriptors already
	// resolved against the frozen rubric, never the raw ids the model returned.
	RubricMatches []contract.RubricMatch `json:"rubric_matches,omitempty"`
	TimedOut      bool                   `json:"timed_out"`
	// Error is a short breadcrumb for a criterion that did not complete, matching
	// AgentResult.Error. json:"-" for the same reason: Dimensions is serialised
	// wholesale to the browser and persisted as JSONB, so a tagged field would
	// ship raw provider error text everywhere and store it forever.
	Error string `json:"-"`
}

// HolisticSwarmResult aggregates the holistic agent results.
//
// KEEP IN SYNC WITH SwarmResult in swarm.go — see TestSwarmAndHolisticAgreeOnBandContract,
// which drives both through the same fault matrix and fails when they disagree.
type HolisticSwarmResult struct {
	Status  string `json:"status"` // "completed" or "failed"
	Partial bool   `json:"partial"`
	// CompletedCount is how many criteria produced a real score, so a client can
	// render "2 of 4 criteria" without recounting the map. Its absence is why
	// `partial` -- a boolean no consumer is obliged to read -- was the only signal.
	CompletedCount int `json:"completed_count"`
	// OverallBand is a pointer for the reason spelled out at SwarmResult.OverallBand:
	// with a plain float64, "no aggregate was computed" and "the aggregate is 0.0"
	// are the same value. This path had the plain float64 and returned 0.0 when
	// every agent failed -- and services/exam persists that number to
	// exam_results.band_score as the candidate's official IELTS band.
	OverallBand     *float64                       `json:"overall_band,omitempty"`
	Dimensions      map[string]HolisticAgentResult `json:"dimensions"`
	OverallFeedback string                         `json:"overall_feedback"`
}

func evaluateHolisticCriterion(ctx context.Context, client LLMClient, criterion, systemPrompt, concatenatedTranscript string, features *ProsodyFeatures) (HolisticAgentResult, error) {
	// GOA-133: the measured feature block, for the criteria defined over
	// acoustics. nil renders nothing at all -- never zeros. See evaluateCriterion
	// in agents.go for why that distinction matters.
	var prosody string
	if features != nil {
		prosody = features.Render() + "\n"
	}

	// SPEAK-EVAL-003: the frozen descriptors, with ids, appended so the model can
	// only cite what it was given.
	grounded := groundedPromptFor(systemPrompt, criterion)

	// The spec is sent TWICE, deliberately, and both copies are load-bearing.
	//
	// The opus-4-8 gateway intermittently drops the system role and falls back to
	// a generic identity; the model then replies "I don't have any IELTS grading
	// instructions in my system prompt" as prose, which fails JSON parsing. So the
	// full spec is also inlined into the user turn, which the gateway always
	// honours, and the task is fully specified either way.
	//
	// The inlined copy is the GROUNDED prompt, not the bare one. Inlining the bare
	// spec would mean that on exactly the requests where the system role was
	// dropped, the model also lost the rubric descriptors -- so its citations would
	// be invented on precisely the calls that already went wrong.
	//
	// Never reference "your system prompt" in this text: when it has been dropped,
	// that phrasing makes the model refuse instead of grade.
	userPrompt := fmt.Sprintf(
		"%s\n\n"+
			"Grade the following IELTS candidate transcript using the rubric and JSON "+
			"schema above. Output ONLY the raw JSON object — no preamble, no "+
			"explanation, no markdown fences. If the transcript is short, still "+
			"return a best-effort band; do not ask for more information.\n\n"+
			"%sCandidate Transcript (All Parts):\n%s",
		grounded, prosody, concatenatedTranscript)

	res, err := client.StreamCompletion(ctx, grounded, userPrompt)
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
		RubricMatches   []rawRubricMatch    `json:"rubric_matches"`
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
		RubricMatches:   parseRubricMatches(parsed.RubricMatches, canonicalCriterionID[criterion]),
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
func evaluateHolisticCriterionCapped(ctx context.Context, client LLMClient, criterion, systemPrompt, concatenatedTranscript string, features *ProsodyFeatures) (HolisticAgentResult, error) {
	attemptCtx, cancel := context.WithTimeout(ctx, attemptTimeout)
	defer cancel()
	return evaluateHolisticCriterion(attemptCtx, client, criterion, systemPrompt, concatenatedTranscript, features)
}

// EvaluateHolisticSwarm orchestrates parallel evaluations for the full exam.
func EvaluateHolisticSwarm(ctx context.Context, client LLMClient, concatenatedTranscript string, features *ProsodyFeatures) (HolisticSwarmResult, error) {
	start := time.Now()

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

	runAgent := func(criterionName string, systemPrompt string, agentFeatures *ProsodyFeatures) {
		defer wg.Done()

		resChan := make(chan HolisticAgentResult, 1)
		errChan := make(chan error, 1)

		go func() {
			res, err := evaluateHolisticCriterionCapped(ctx, client, criterionName, systemPrompt, concatenatedTranscript, agentFeatures)
			if err != nil {
				errChan <- err
				return
			}
			resChan <- res
		}()

		var outcome HolisticAgentResult
		select {
		case res := <-resChan:
			outcome = res
		case err := <-errChan:
			// The error is LOGGED and carried, not discarded. It used to be
			// dropped on the floor with TimedOut set to true, so an expired
			// credential, a malformed response (BUG-057's shape) and a genuinely
			// slow provider produced identical output -- and raising the deadline
			// could never fix two of the three. swarm.go learned this in GOA-032;
			// the lesson did not reach this file.
			log.Error().
				Err(err).
				Str("criterion", criterionName).
				Dur("failed_after", time.Since(start)).
				Msg("Holistic evaluation agent failed")
			outcome = HolisticAgentResult{
				Criterion:       criterionName,
				Band:            0.0,
				OverallFeedback: "Evaluation unavailable due to an internal error.",
				Error:           errorSummary(err),
				// TimedOut stays true, matching swarm.go: despite its name the
				// field means "produced no score", and it is the flag both the
				// aggregation below and the exam service's CriterionDetail read.
				// Error is what distinguishes a provider failure from a deadline.
				// Renaming the field would be clearer and would break the wire
				// contract with services/exam; that belongs in the follow-up that
				// merges the two paths.
				TimedOut: true,
			}
		case <-ctx.Done():
			log.Warn().
				Str("criterion", criterionName).
				Dur("failed_after", time.Since(start)).
				Msg("Holistic evaluation agent exceeded the swarm deadline")
			outcome = HolisticAgentResult{
				Criterion:       criterionName,
				Band:            0.0,
				OverallFeedback: "Evaluation unavailable due to response timeout.",
				Error:           AgentErrorDeadline,
				TimedOut:        true,
			}
		}

		mu.Lock()
		results[criterionName] = outcome
		mu.Unlock()
	}

	// Indexed off CriterionOrder so the names here cannot drift from the ones
	// swarm.go, the feedback summary and the exam service all use.
	// Only Fluency and Pronunciation receive the feature block. Lexical and
	// Grammar have no use for it and it is pure token cost on every call.
	go runAgent(CriterionOrder[0], HolisticFluencySystemPrompt, features)
	go runAgent(CriterionOrder[1], HolisticLexicalSystemPrompt, nil)
	go runAgent(CriterionOrder[2], HolisticGrammarSystemPrompt, nil)
	go runAgent(CriterionOrder[3], HolisticPronunciationSystemPrompt, features)

	wg.Wait()

	// Same aggregateBands call as EvaluateSwarm. Not a copy of it: the constant
	// was already shared, the arithmetic around it was not, and sharing only the
	// constant is what let the two paths agree on the threshold while
	// disagreeing about everything else.
	var scored []float64
	for _, res := range results {
		if !res.TimedOut {
			scored = append(scored, res.Band)
		}
	}
	agg := aggregateBands(scored, len(CriterionOrder))
	completedCount := agg.CompletedCount
	partial := agg.Partial

	if completedCount == 0 {
		return HolisticSwarmResult{
			Status:          "failed",
			Partial:         false,
			CompletedCount:  0,
			OverallBand:     nil,
			Dimensions:      results,
			OverallFeedback: "Evaluation completely failed due to timeouts or internal errors on all criteria.",
		}, fmt.Errorf("all evaluation agents timed out or failed")
	}

	// Nil below the threshold, for the reason spelled out in aggregateBands.
	overallBand := agg.OverallBand

	// CriterionOrder rather than a local slice literal, for the reason it exists:
	// ranging a map is randomised in Go, and a duplicated order list is one more
	// thing to keep in sync.
	var feedbackLines []string
	for _, name := range CriterionOrder {
		res := results[name]
		if res.TimedOut {
			// Printing "Band 0.0" for an agent that never scored restates the
			// BUG-055 lie in prose, where no downstream type-safety can catch it.
			feedbackLines = append(feedbackLines, fmt.Sprintf("- **%s**: %s", name, res.OverallFeedback))
			continue
		}
		feedbackLines = append(feedbackLines, fmt.Sprintf("- **%s** (Band %.1f): %s", name, res.Band, res.OverallFeedback))
	}
	overallFeedback := "### IELTS Speaking Rubric Evaluation Summary:\n\n" + strings.Join(feedbackLines, "\n")

	return HolisticSwarmResult{
		Status:          "completed",
		Partial:         partial,
		CompletedCount:  completedCount,
		OverallBand:     overallBand,
		Dimensions:      results,
		OverallFeedback: overallFeedback,
	}, nil
}
