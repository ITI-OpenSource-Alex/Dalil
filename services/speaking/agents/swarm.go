package agents

import (
	"context"
	"fmt"
	"strings"
	"sync"
)

// SwarmResult represents the aggregated output of our parallel evaluation swarm
type SwarmResult struct {
	Status          string                 `json:"status"` // "completed" or "failed"
	Partial         bool                   `json:"partial"`
	OverallBand     float64                `json:"overall_band"`
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

// EvaluateSwarm orchestrates parallel evaluations, handles partial timeouts, and aggregates scores
func EvaluateSwarm(ctx context.Context, client LLMClient, questionPrompt, questionType, transcript string) (SwarmResult, error) {
	var wg sync.WaitGroup
	wg.Add(4)

	var mu sync.Mutex
	results := make(map[string]AgentResult)

	// Helper to coordinate parallel execution and individual timeout fallback
	runAgent := func(criterionName string, evalFn func(context.Context, LLMClient, string, string, string) (AgentResult, error)) {
		defer wg.Done()

		resChan := make(chan AgentResult, 1)
		errChan := make(chan error, 1)

		go func() {
			res, err := evalFn(ctx, client, questionPrompt, questionType, transcript)
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
		case <-errChan:
			// Degrade gracefully on API errors, fallback to empty result
			mu.Lock()
			results[criterionName] = AgentResult{
				Criterion: criterionName,
				Band:      0.0,
				Feedback:  "Evaluation unavailable due to an internal error.",
				TimedOut:  true,
			}
			mu.Unlock()
		case <-ctx.Done():
			// Exceeded timeout context budget
			mu.Lock()
			results[criterionName] = AgentResult{
				Criterion: criterionName,
				Band:      0.0,
				Feedback:  "Evaluation unavailable due to response timeout.",
				TimedOut:  true,
			}
			mu.Unlock()
		}
	}

	// Trigger 4 specialized evaluations concurrently
	go runAgent("Fluency and Coherence", EvaluateFluency)
	go runAgent("Lexical Resource", EvaluateLexical)
	go runAgent("Grammatical Range and Accuracy", EvaluateGrammar)
	go runAgent("Pronunciation", EvaluatePronunciation)

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

	// If all 4 agents failed, return top-level failed status
	if completedCount == 0 {
		return SwarmResult{
			Status:          "failed",
			Partial:         false,
			OverallBand:     0.0,
			Dimensions:      results,
			OverallFeedback: "Evaluation completely failed due to timeouts or internal errors on all criteria.",
		}, fmt.Errorf("all evaluation agents timed out or failed")
	}

	// Average only successfully completed criteria
	avgBand := totalBand / float64(completedCount)
	overallBand := RoundIELTSBand(avgBand)

	// Synthesize overall feedback deterministically using templates
	var feedbackLines []string
	for _, name := range []string{"Fluency and Coherence", "Lexical Resource", "Grammatical Range and Accuracy", "Pronunciation"} {
		res := results[name]
		feedbackLines = append(feedbackLines, fmt.Sprintf("- **%s** (Band %.1f): %s", name, res.Band, res.Feedback))
	}
	overallFeedback := "### IELTS Speaking Rubric Evaluation Summary:\n\n" + strings.Join(feedbackLines, "\n")

	return SwarmResult{
		Status:          "completed",
		Partial:         partial,
		OverallBand:     overallBand,
		Dimensions:      results,
		OverallFeedback: overallFeedback,
	}, nil
}
