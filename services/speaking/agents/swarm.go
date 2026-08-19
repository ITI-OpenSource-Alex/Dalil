package agents

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
)

// maxAgentErrorChars bounds what a provider error is allowed to contribute to a
// response the client sees. Provider errors can be long and can echo request
// content back; a diagnostic breadcrumb is useful, a wall of text on the wire
// is not.
const maxAgentErrorChars = 200

// AgentErrorDeadline marks a criterion that ran out of budget rather than
// failing. Callers classify on this exact value, so it is a constant.
const AgentErrorDeadline = "deadline exceeded"

// AgentErrorInsufficientEvidence marks a criterion that could not be assessed
// because the evidence it is defined over was never supplied.
//
// Distinct from a provider failure and from a deadline, because it is neither:
// nothing went wrong, and retrying cannot help. The input simply did not
// contain what this criterion measures.
//
// SPEAK-EVAL-007 found why this is needed. Asked to judge Pronunciation from a
// transcript with no acoustic features, the agent wrote "pronunciation cannot
// be assessed ... no measured speech features were supplied" -- and returned
// band 0.0. Band 0.0 is a legal IELTS value, so the contract accepted it as a
// real score and averaged it in, dragging a band 8 candidate to 5.5. The
// contract defends against an agent that FAILS; it had no defence against one
// that succeeds while saying it has no evidence. Refusing before the model is
// called is the only place that can be closed.
const AgentErrorInsufficientEvidence = "insufficient evidence"

// errorSummary renders a provider failure as a short, safe breadcrumb.
func errorSummary(err error) string {
	if err == nil {
		return ""
	}
	msg := err.Error()
	if len(msg) > maxAgentErrorChars {
		msg = msg[:maxAgentErrorChars] + "..."
	}
	return msg
}

// MinCriteriaForOverallBand is how many of the four criteria must complete
// before an aggregate band means anything (GOA-032, BUG-040).
//
// Below this the payload carries the criteria that did land and no overall
// figure. Averaging one or two surviving criteria and presenting the result as
// an IELTS band is not a partial answer, it is a wrong one: a candidate whose
// Fluency and Lexical agents timed out would read a "band" derived entirely
// from Pronunciation.
const MinCriteriaForOverallBand = 3

// CriterionOrder fixes the presentation order of the four criteria. Ranging a
// map is randomised in Go, so without this the summary feedback reordered
// itself on every request.
var CriterionOrder = [4]string{
	"Fluency and Coherence",
	"Lexical Resource",
	"Grammatical Range and Accuracy",
	"Pronunciation",
}

// CriterionEvent carries one agent's outcome to the caller the moment it lands,
// rather than after wg.Wait().
type CriterionEvent struct {
	Criterion string
	Result    AgentResult
	// ElapsedMs is measured from swarm start, not from this agent's own start.
	// The four launch together, so a per-agent origin would produce four numbers
	// that cannot be compared with each other or with time_to_first_criterion.
	ElapsedMs int64
}

// SwarmResult represents the aggregated output of our parallel evaluation swarm
type SwarmResult struct {
	Status  string `json:"status"` // "completed" or "failed"
	Partial bool   `json:"partial"`
	// CompletedCount is how many criteria produced a real score. Exposed so a
	// client can render "3 of 4 criteria" without recounting the map.
	CompletedCount int `json:"completed_count"`
	// OverallBand is a pointer so "no aggregate was computed" is distinguishable
	// from "the aggregate is 0.0". With a plain float64 those two are the same
	// value, which is precisely the class of defect BUG-055 was: a score the
	// model never produced, reported as a real one. omitempty drops the key
	// entirely rather than sending null, so a client that checks for the field's
	// presence and one that checks for a falsy value both behave.
	OverallBand     *float64               `json:"overall_band,omitempty"`
	Dimensions      map[string]AgentResult `json:"dimensions"`
	OverallFeedback string                 `json:"overall_feedback"`
}

// RoundIELTSBand implements the official IELTS half-up rounding rules
func RoundIELTSBand(average float64) float64 {
	intPart := float64(int(average))
	decPart := average - intPart

	if decPart < 0.25 {
		return intPart
	} else if decPart < 0.75 {
		return intPart + 0.5
	} else {
		return intPart + 1.0
	}
}

// EvaluateSwarm orchestrates parallel evaluations, emits each criterion as it
// completes, handles partial timeouts, and aggregates the scores.
//
// onCriterion may be nil. When non-nil it is invoked exactly once per criterion
// -- including for the timeout and error paths -- from the completing agent's
// own goroutine. It is therefore on that agent's latency path and must not
// block for long. It is deliberately called *outside* the results mutex: the
// production callback writes to a WebSocket send channel, and holding the mutex
// across that would let one slow consumer stall the other three agents.
func EvaluateSwarm(
	ctx context.Context,
	client LLMClient,
	questionPrompt, questionType, transcript string,
	features *ProsodyFeatures,
	onCriterion func(CriterionEvent),
) (SwarmResult, error) {
	start := time.Now()

	var wg sync.WaitGroup
	wg.Add(4)

	var mu sync.Mutex
	results := make(map[string]AgentResult)

	// Helper to coordinate parallel execution and individual timeout fallback
	runAgent := func(criterionName string, evalFn func(context.Context, LLMClient, string, string, string, *ProsodyFeatures) (AgentResult, error)) {
		defer wg.Done()

		resChan := make(chan AgentResult, 1)
		errChan := make(chan error, 1)

		go func() {
			res, err := evalFn(ctx, client, questionPrompt, questionType, transcript, features)
			if err != nil {
				errChan <- err
				return
			}
			resChan <- res
		}()

		var outcome AgentResult
		select {
		case res := <-resChan:
			outcome = res
		case err := <-errChan:
			// Degrade gracefully on API errors, fall back to an empty result.
			//
			// The error is LOGGED, not discarded. It used to be dropped on the
			// floor, so an expired provider credential and a genuinely slow
			// provider produced the identical user-facing message and the
			// identical (empty) log output -- diagnosing which one you had
			// required curling the provider by hand. Four agents failing in 2.8s
			// is not a timeout, and the service should be the thing that says so.
			log.Error().
				Err(err).
				Str("criterion", criterionName).
				Dur("failed_after", time.Since(start)).
				Msg("Evaluation agent failed")
			outcome = AgentResult{
				Criterion: criterionName,
				Band:      0.0,
				Feedback:  "Evaluation unavailable due to an internal error.",
				Error:     errorSummary(err),
				TimedOut:  true,
			}
		case <-ctx.Done():
			// Exceeded the timeout context budget
			log.Warn().
				Str("criterion", criterionName).
				Dur("failed_after", time.Since(start)).
				Msg("Evaluation agent exceeded the swarm deadline")
			outcome = AgentResult{
				Criterion: criterionName,
				Band:      0.0,
				Feedback:  "Evaluation unavailable due to response timeout.",
				Error:     AgentErrorDeadline,
				TimedOut:  true,
			}
		}

		mu.Lock()
		results[criterionName] = outcome
		mu.Unlock()

		// Emitted for every terminal path, not just success. The client counts
		// frames to decide whether it has reached MinCriteriaForOverallBand; a
		// criterion that failed silently would leave the UI waiting on a frame
		// that is never coming.
		if onCriterion != nil {
			onCriterion(CriterionEvent{
				Criterion: criterionName,
				Result:    outcome,
				ElapsedMs: time.Since(start).Milliseconds(),
			})
		}
	}

	// Trigger 4 specialized evaluations concurrently
	go runAgent(CriterionOrder[0], EvaluateFluency)
	go runAgent(CriterionOrder[1], EvaluateLexical)
	go runAgent(CriterionOrder[2], EvaluateGrammar)
	go runAgent(CriterionOrder[3], EvaluatePronunciation)

	wg.Wait()

	// The arithmetic lives in aggregateBands (canonical.go), shared with
	// EvaluateHolisticSwarm. It used to be a second copy of these lines, kept
	// aligned by a KEEP IN SYNC comment; GOA-134 is what such a comment is worth
	// as a synchronisation mechanism.
	var scored []float64
	for _, res := range results {
		if !res.TimedOut {
			scored = append(scored, res.Band)
		}
	}
	agg := aggregateBands(scored, len(CriterionOrder))
	completedCount := agg.CompletedCount
	partial := agg.Partial

	// If all 4 agents failed, return top-level failed status. Kept distinct from
	// the "fewer than 3 completed" branch below: the client shows an error for
	// this one and partial results for that one.
	if completedCount == 0 {
		return SwarmResult{
			Status:          "failed",
			Partial:         false,
			CompletedCount:  0,
			OverallBand:     nil,
			Dimensions:      results,
			OverallFeedback: "Evaluation completely failed due to timeouts or internal errors on all criteria.",
		}, fmt.Errorf("all evaluation agents timed out or failed")
	}

	// Nil below the threshold: only successfully completed criteria are averaged,
	// and only once enough of them completed for the average to describe the
	// candidate rather than describe which agents happened to survive.
	overallBand := agg.OverallBand

	// Synthesize overall feedback deterministically using templates
	var feedbackLines []string
	for _, name := range CriterionOrder {
		res := results[name]
		if res.TimedOut {
			// Printing "Band 0.0" for an agent that never scored restates the
			// BUG-055 lie in prose, where no amount of downstream type-safety can
			// catch it.
			feedbackLines = append(feedbackLines, fmt.Sprintf("- **%s**: %s", name, res.Feedback))
			continue
		}
		feedbackLines = append(feedbackLines, fmt.Sprintf("- **%s** (Band %.1f): %s", name, res.Band, res.Feedback))
	}
	overallFeedback := "### IELTS Speaking Rubric Evaluation Summary:\n\n" + strings.Join(feedbackLines, "\n")

	return SwarmResult{
		Status:          "completed",
		Partial:         partial,
		CompletedCount:  completedCount,
		OverallBand:     overallBand,
		Dimensions:      results,
		OverallFeedback: overallFeedback,
	}, nil
}
