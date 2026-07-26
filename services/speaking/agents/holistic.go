// agents/holistic.go
package agents

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
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
	// Build prompt
	userPrompt := fmt.Sprintf("Candidate Transcript (All Parts):\n%s", concatenatedTranscript)
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

// EvaluateHolisticSwarm orchestrates parallel evaluations for the full exam.
func EvaluateHolisticSwarm(ctx context.Context, client LLMClient, concatenatedTranscript string) (HolisticSwarmResult, error) {
	var wg sync.WaitGroup
	wg.Add(4)

	var mu sync.Mutex
	results := make(map[string]HolisticAgentResult)

	runAgent := func(criterionName string, systemPrompt string) {
		defer wg.Done()

		resChan := make(chan HolisticAgentResult, 1)
		errChan := make(chan error, 1)

		go func() {
			res, err := evaluateHolisticCriterion(ctx, client, criterionName, systemPrompt, concatenatedTranscript)
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
			mu.Lock()
			results[criterionName] = HolisticAgentResult{
				Criterion:       criterionName,
				Band:            0.0,
				OverallFeedback: "Evaluation unavailable due to an internal error.",
				TimedOut:        true,
			}
			mu.Unlock()
		case <-ctx.Done():
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
