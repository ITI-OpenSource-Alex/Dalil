package agents

import (
	"context"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

// SelectiveDelayMockClient delays completion calls targeting a specific criterion
type SelectiveDelayMockClient struct {
	DelayCriteria string
	DelayDuration time.Duration
}

func (m *SelectiveDelayMockClient) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	// If evaluating the target criterion, simulate delay
	if strings.Contains(systemPrompt, m.DelayCriteria) {
		select {
		case <-ctx.Done():
			return llm.CompletionResult{}, ctx.Err()
		case <-time.After(m.DelayDuration):
		}
	}
	return llm.CompletionResult{
		Text:             `{"band": 7.0, "feedback": "Completed successfully.", "examples": ["sample example"]}`,
		PromptTokens:     10,
		CompletionTokens: 10,
		LatencyMs:        100,
	}, nil
}

func TestSwarm_AllSuccess(t *testing.T) {
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": 7.0, "feedback": "Good job.", "examples": []}`,
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	res, err := EvaluateSwarm(ctx, mockClient, "Describe a standard day.", "IELTS Part 2", "I wake up early...")
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

func TestSwarm_RoundingRules(t *testing.T) {
	tests := []struct {
		name         string
		scores       []float64
		expectedBand float64
	}{
		{"Round down (<0.25)", []float64{6.0, 6.0, 6.0, 6.5}, 6.0},              // avg = 6.125 -> 6.0
		{"Round up to half (>=0.25)", []float64{6.0, 6.0, 6.5, 6.5}, 6.5},       // avg = 6.25 -> 6.5
		{"Round down to half (<0.75)", []float64{6.5, 6.5, 6.5, 7.0}, 6.5},      // avg = 6.625 -> 6.5
		{"Round up to next whole (>=0.75)", []float64{6.5, 6.5, 7.0, 7.0}, 7.0}, // avg = 6.75 -> 7.0
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			avg := (tt.scores[0] + tt.scores[1] + tt.scores[2] + tt.scores[3]) / 4.0
			rounded := RoundIELTSBand(avg)
			if rounded != tt.expectedBand {
				t.Errorf("expected RoundIELTSBand(%v) = %v, got %v", avg, tt.expectedBand, rounded)
			}
		})
	}
}

func TestSwarm_PartialTimeout(t *testing.T) {
	// Delays only the Grammar agent by 200ms. We set a 50ms context timeout.
	mockClient := &SelectiveDelayMockClient{
		DelayCriteria: "Grammatical Range and Accuracy",
		DelayDuration: 200 * time.Millisecond,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	res, err := EvaluateSwarm(ctx, mockClient, "Describe a book.", "IELTS Part 2", "I read a book...")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	// The session completes because we allow partial timeout fallback
	if res.Status != "completed" {
		t.Errorf("expected status 'completed', got '%s'", res.Status)
	}
	if !res.Partial {
		t.Errorf("expected partial true because one agent timed out")
	}

	// 3 successful agents returned band 7.0. Average should be 7.0
	if res.OverallBand != 7.0 {
		t.Errorf("expected overall band 7.0, got %v", res.OverallBand)
	}

	// Assert that Grammar timed out and fallback values were applied
	gRes := res.Dimensions["Grammatical Range and Accuracy"]
	if !gRes.TimedOut {
		t.Errorf("expected grammar agent to be timed out")
	}
	if gRes.Band != 0.0 {
		t.Errorf("expected fallback band score 0.0 for timed-out agent, got %v", gRes.Band)
	}
}

func TestSwarm_AllFailed(t *testing.T) {
	// Immediately cancelled context (simulates full failure)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": 7.0, "feedback": "Good job.", "examples": []}`,
		},
	}

	res, err := EvaluateSwarm(ctx, mockClient, "Prompt", "Type", "Transcript")
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

func TestSwarm_GoroutineLeak(t *testing.T) {
	// 1. Capture baseline count
	baseline := runtime.NumGoroutine()

	// 2. Run a timeout scenario
	mockClient := &SelectiveDelayMockClient{
		DelayCriteria: "Grammatical Range and Accuracy",
		DelayDuration: 200 * time.Millisecond,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	_, _ = EvaluateSwarm(ctx, mockClient, "Prompt", "Type", "Transcript")

	// 3. Poll to verify goroutines settle back (allowing short buffer for teardown)
	success := false
	for i := 0; i < 10; i++ {
		time.Sleep(50 * time.Millisecond)
		current := runtime.NumGoroutine()
		if current <= baseline+2 { // allow delta of 2 for garbage collector or test runner threads
			success = true
			break
		}
	}

	if !success {
		t.Errorf("goroutines leaked (baseline: %d, final: %d)", baseline, runtime.NumGoroutine())
	}
}
