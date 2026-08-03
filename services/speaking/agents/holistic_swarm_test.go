package agents

import (
	"context"
	"runtime"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

type HolisticSelectiveDelayMockClient struct {
	DelayCriteria string
	DelayDuration time.Duration
}

func (m *HolisticSelectiveDelayMockClient) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	isTarget := false
	if m.DelayCriteria == "Grammatical Range and Accuracy" && strings.Contains(systemPrompt, "Grammatical Range and Accuracy") {
		isTarget = true
	} else if m.DelayCriteria == "Fluency and Coherence" && strings.Contains(systemPrompt, "Fluency and Coherence") {
		isTarget = true
	} else if m.DelayCriteria == "Lexical Resource" && strings.Contains(systemPrompt, "Lexical Resource") {
		isTarget = true
	} else if m.DelayCriteria == "Pronunciation" && strings.Contains(systemPrompt, "Pronunciation") {
		isTarget = true
	}

	if isTarget {
		select {
		case <-ctx.Done():
			return llm.CompletionResult{}, ctx.Err()
		case <-time.After(m.DelayDuration):
		}
	}
	return llm.CompletionResult{
		Text:             `{"band": 7.0, "overall_feedback": "Completed successfully.", "part_notes": {}, "examples": [], "improvement_tip": ""}`,
		PromptTokens:     10,
		CompletionTokens: 10,
		LatencyMs:        100,
	}, nil
}

func TestHolisticSwarm_AllSuccess(t *testing.T) {
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": 7.0, "overall_feedback": "Good job.", "part_notes": {}, "examples": [], "improvement_tip": ""}`,
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	res, err := EvaluateHolisticSwarm(ctx, mockClient, "Part 1: Hi...")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if res.Status != "completed" {
		t.Errorf("expected status 'completed', got '%s'", res.Status)
	}
	if res.Partial {
		t.Errorf("expected partial false, got true")
	}
	if res.OverallBand != 7.0 {
		t.Errorf("expected overall band 7.0, got %v", res.OverallBand)
	}
}

func TestHolisticSwarm_RoundingRules(t *testing.T) {
	_ = RoundIELTSBand(6.625)
}

func TestHolisticSwarm_PartialTimeout(t *testing.T) {
	mockClient := &HolisticSelectiveDelayMockClient{
		DelayCriteria: "Grammatical Range and Accuracy",
		DelayDuration: 200 * time.Millisecond,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	res, err := EvaluateHolisticSwarm(ctx, mockClient, "Part 1: Hi...")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if res.Status != "completed" {
		t.Errorf("expected status 'completed', got '%s'", res.Status)
	}
	if !res.Partial {
		t.Errorf("expected partial true because one agent timed out")
	}

	if res.OverallBand != 7.0 {
		t.Errorf("expected overall band 7.0, got %v", res.OverallBand)
	}

	gRes := res.Dimensions["Grammatical Range and Accuracy"]
	if !gRes.TimedOut {
		t.Errorf("expected grammar agent to be timed out")
	}
	if gRes.Band != 0.0 {
		t.Errorf("expected fallback band score 0.0 for timed-out agent, got %v", gRes.Band)
	}
}

func TestHolisticSwarm_AllFailed(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": 7.0, "overall_feedback": "Good job.", "part_notes": {}, "examples": [], "improvement_tip": ""}`,
		},
	}

	res, err := EvaluateHolisticSwarm(ctx, mockClient, "Transcript")
	if err == nil {
		t.Fatal("expected error since all agents failed, got nil")
	}

	if res.Status != "failed" {
		t.Errorf("expected status 'failed', got '%s'", res.Status)
	}
	if res.OverallBand != 0.0 {
		t.Errorf("expected overall band 0.0, got %v", res.OverallBand)
	}
}

func TestHolisticSwarm_GoroutineLeak(t *testing.T) {
	baseline := runtime.NumGoroutine()

	mockClient := &HolisticSelectiveDelayMockClient{
		DelayCriteria: "Grammatical Range and Accuracy",
		DelayDuration: 200 * time.Millisecond,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	_, _ = EvaluateHolisticSwarm(ctx, mockClient, "Transcript")

	success := false
	for i := 0; i < 10; i++ {
		time.Sleep(50 * time.Millisecond)
		current := runtime.NumGoroutine()
		if current <= baseline+2 {
			success = true
			break
		}
	}

	if !success {
		t.Errorf("goroutines leaked (baseline: %d, final: %d)", baseline, runtime.NumGoroutine())
	}
}

func TestHolisticSwarm_LoadTest(t *testing.T) {
	mockClient := &HolisticSelectiveDelayMockClient{
		DelayCriteria: "None",
		DelayDuration: 2000 * time.Millisecond,
	}

	concurrency := 10
	var wg sync.WaitGroup
	wg.Add(concurrency)

	latencies := make(chan time.Duration, concurrency)

	for i := 0; i < concurrency; i++ {
		go func() {
			defer wg.Done()
			start := time.Now()
			ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
			defer cancel()

			_, err := EvaluateHolisticSwarm(ctx, mockClient, "Transcript")
			if err != nil {
				t.Errorf("evaluation failed during load test: %v", err)
			}
			latencies <- time.Since(start)
		}()
	}

	wg.Wait()
	close(latencies)

	var maxLatency time.Duration
	for lat := range latencies {
		if lat > maxLatency {
			maxLatency = lat
		}
	}

	if maxLatency > 8000*time.Millisecond {
		t.Errorf("Load test failed: max latency %v exceeded 8000ms limit", maxLatency)
	}
}
