package agents

import (
	"context"
	"encoding/json"
	"runtime"
	"strings"
	"sync"
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
		FirstTokenMs:     40,
	}, nil
}

// GatedMockClient blocks the agent for one named criterion until Release is
// called. It makes ordering assertions deterministic: no sleeps, no timing
// tolerances, so the test cannot flake on a slow CI box.
type GatedMockClient struct {
	GateCriteria string
	gate         chan struct{}
	once         sync.Once
}

func NewGatedMockClient(criteria string) *GatedMockClient {
	return &GatedMockClient{GateCriteria: criteria, gate: make(chan struct{})}
}

func (m *GatedMockClient) Release() { m.once.Do(func() { close(m.gate) }) }

func (m *GatedMockClient) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	if strings.Contains(systemPrompt, m.GateCriteria) {
		select {
		case <-ctx.Done():
			return llm.CompletionResult{}, ctx.Err()
		case <-m.gate:
		}
	}
	return llm.CompletionResult{
		Text:             `{"band": 7.0, "feedback": "Completed successfully.", "examples": []}`,
		PromptTokens:     10,
		CompletionTokens: 10,
		LatencyMs:        100,
		FirstTokenMs:     40,
	}, nil
}

// FailingCriteriaMock errors for the named criteria and succeeds for the rest,
// so a test can pick exactly how many criteria complete.
type FailingCriteriaMock struct {
	FailCriteria []string
	Band         float64
}

func (m *FailingCriteriaMock) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	for _, c := range m.FailCriteria {
		if strings.Contains(systemPrompt, c) {
			return llm.CompletionResult{}, context.DeadlineExceeded
		}
	}
	band := m.Band
	if band == 0 {
		band = 7.0
	}
	payload, _ := json.Marshal(map[string]any{"band": band, "feedback": "ok", "examples": []string{}})
	return llm.CompletionResult{Text: string(payload), LatencyMs: 100, FirstTokenMs: 40}, nil
}

// bandOrFail dereferences OverallBand, failing the test when it is absent.
func bandOrFail(t *testing.T, res SwarmResult) float64 {
	t.Helper()
	if res.OverallBand == nil {
		t.Fatalf("expected an overall band, got none (completed %d)", res.CompletedCount)
	}
	return *res.OverallBand
}

func TestSwarm_AllSuccess(t *testing.T) {
	mockClient := &MockLLMClient{
		Result: llm.CompletionResult{
			Text: `{"band": 7.0, "feedback": "Good job.", "examples": []}`,
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	res, err := EvaluateSwarm(ctx, mockClient, "Describe a standard day.", "IELTS Part 2", "I wake up early...", nil)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if res.Status != "completed" {
		t.Errorf("expected status 'completed', got '%s'", res.Status)
	}
	if res.Partial {
		t.Errorf("expected partial false, got true")
	}
	if res.CompletedCount != 4 {
		t.Errorf("expected 4 completed criteria, got %d", res.CompletedCount)
	}
	if got := bandOrFail(t, res); got != 7.0 {
		t.Errorf("expected overall band 7.0, got %v", got)
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

	res, err := EvaluateSwarm(ctx, mockClient, "Describe a book.", "IELTS Part 2", "I read a book...", nil)
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

	// 3 successful agents returned band 7.0, which is exactly the threshold, so
	// an overall band IS emitted here.
	if got := bandOrFail(t, res); got != 7.0 {
		t.Errorf("expected overall band 7.0, got %v", got)
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

	res, err := EvaluateSwarm(ctx, mockClient, "Prompt", "Type", "Transcript", nil)
	if err == nil {
		t.Fatal("expected error since all agents failed, got nil")
	}

	if res.Status != "failed" {
		t.Errorf("expected status 'failed', got '%s'", res.Status)
	}
	if res.OverallBand != nil {
		t.Errorf("expected no overall band on total failure, got %v", *res.OverallBand)
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

	_, _ = EvaluateSwarm(ctx, mockClient, "Prompt", "Type", "Transcript", nil)

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

// --- GOA-032: per-criterion streaming ---------------------------------------

// TestSwarm_EmitsBeforeSlowestReturns is the ticket's headline requirement:
// "a criterion frame reaches the client before the slowest agent has returned".
//
// It is gated rather than timed, so it proves ordering rather than merely
// observing it on a fast machine.
func TestSwarm_EmitsBeforeSlowestReturns(t *testing.T) {
	const slowest = "Pronunciation"
	mockClient := NewGatedMockClient(slowest)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	events := make(chan CriterionEvent, 4)
	done := make(chan SwarmResult, 1)

	go func() {
		res, _ := EvaluateSwarm(ctx, mockClient, "Prompt", "Type", "Transcript", func(ev CriterionEvent) {
			events <- ev
		})
		done <- res
	}()

	// The other three must all arrive while Pronunciation is still blocked. If
	// emission happened after wg.Wait() this deadlocks and the test times out --
	// which is precisely the regression we want it to catch.
	seen := make(map[string]bool)
	for i := 0; i < 3; i++ {
		select {
		case ev := <-events:
			seen[ev.Criterion] = true
		case <-time.After(3 * time.Second):
			t.Fatalf("only %d criteria streamed before the slowest agent returned; want 3", i)
		}
	}
	if seen[slowest] {
		t.Fatalf("the gated agent emitted before it was released")
	}

	// Nothing has returned yet.
	select {
	case res := <-done:
		t.Fatalf("EvaluateSwarm returned before the slowest agent finished: %+v", res)
	default:
	}

	mockClient.Release()

	select {
	case ev := <-events:
		if ev.Criterion != slowest {
			t.Fatalf("expected the fourth event to be %q, got %q", slowest, ev.Criterion)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("the released agent never emitted")
	}

	select {
	case res := <-done:
		if res.CompletedCount != 4 {
			t.Errorf("expected 4 completed criteria, got %d", res.CompletedCount)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("EvaluateSwarm never returned after release")
	}
}

// TestSwarm_EmitsExactlyOncePerCriterionIncludingFailures guards the invariant
// the client depends on to count toward MinCriteriaForOverallBand: a criterion
// that fails must still produce a frame, or the UI waits forever on a fourth
// event that is never coming.
func TestSwarm_EmitsExactlyOncePerCriterionIncludingFailures(t *testing.T) {
	mockClient := &FailingCriteriaMock{
		FailCriteria: []string{"Lexical Resource", "Pronunciation"},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var mu sync.Mutex
	counts := map[string]int{}

	res, err := EvaluateSwarm(ctx, mockClient, "Prompt", "Type", "Transcript", func(ev CriterionEvent) {
		mu.Lock()
		counts[ev.Criterion]++
		mu.Unlock()
	})
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	mu.Lock()
	defer mu.Unlock()
	if len(counts) != 4 {
		t.Fatalf("expected events for all 4 criteria, got %d: %v", len(counts), counts)
	}
	for _, name := range CriterionOrder {
		if counts[name] != 1 {
			t.Errorf("criterion %q emitted %d times, want exactly 1", name, counts[name])
		}
	}
	if res.CompletedCount != 2 {
		t.Errorf("expected 2 completed criteria, got %d", res.CompletedCount)
	}
}

// TestSwarm_OverallBandGating covers BUG-040 directly: a band derived from
// fewer than 3 criteria must not be presented as an overall band.
func TestSwarm_OverallBandGating(t *testing.T) {
	tests := []struct {
		name       string
		fail       []string
		wantBand   bool
		wantCount  int
		wantStatus string
	}{
		{"four complete", nil, true, 4, "completed"},
		{"three complete", []string{"Pronunciation"}, true, 3, "completed"},
		{"two complete", []string{"Pronunciation", "Lexical Resource"}, false, 2, "completed"},
		{"one complete", []string{"Pronunciation", "Lexical Resource", "Fluency and Coherence"}, false, 1, "completed"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()

			res, err := EvaluateSwarm(ctx, &FailingCriteriaMock{FailCriteria: tt.fail},
				"Prompt", "Type", "Transcript", nil)
			if err != nil {
				t.Fatalf("expected no error, got %v", err)
			}
			if res.Status != tt.wantStatus {
				t.Errorf("status = %q, want %q", res.Status, tt.wantStatus)
			}
			if res.CompletedCount != tt.wantCount {
				t.Errorf("completed = %d, want %d", res.CompletedCount, tt.wantCount)
			}
			if tt.wantBand && res.OverallBand == nil {
				t.Errorf("expected an overall band with %d criteria completed", res.CompletedCount)
			}
			if !tt.wantBand && res.OverallBand != nil {
				t.Errorf("expected NO overall band with %d criteria completed, got %v",
					res.CompletedCount, *res.OverallBand)
			}
		})
	}
}

// TestSwarm_OverallBandOmittedFromJSON asserts the wire format, not just the
// Go value. A client checking `"overall_band" in payload` and one checking for
// a truthy value must both see "absent" -- a serialised 0.0 would satisfy
// neither honestly.
func TestSwarm_OverallBandOmittedFromJSON(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	res, err := EvaluateSwarm(ctx,
		&FailingCriteriaMock{FailCriteria: []string{"Pronunciation", "Lexical Resource"}},
		"Prompt", "Type", "Transcript", nil)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	raw, err := json.Marshal(res)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, present := decoded["overall_band"]; present {
		t.Errorf("overall_band must be absent below %d completed criteria, payload was %s",
			MinCriteriaForOverallBand, raw)
	}

	// And present when it should be.
	full, err := EvaluateSwarm(ctx, &FailingCriteriaMock{}, "Prompt", "Type", "Transcript", nil)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	rawFull, _ := json.Marshal(full)
	var decodedFull map[string]any
	_ = json.Unmarshal(rawFull, &decodedFull)
	if _, present := decodedFull["overall_band"]; !present {
		t.Errorf("overall_band must be present with 4 completed criteria, payload was %s", rawFull)
	}
}

// TestSwarm_FeedbackOmitsBandForTimedOutCriteria stops the summary prose from
// restating a score the model never produced.
func TestSwarm_FeedbackOmitsBandForTimedOutCriteria(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	res, err := EvaluateSwarm(ctx, &FailingCriteriaMock{FailCriteria: []string{"Pronunciation"}},
		"Prompt", "Type", "Transcript", nil)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if strings.Contains(res.OverallFeedback, "**Pronunciation** (Band 0.0)") {
		t.Errorf("timed-out criterion reported as Band 0.0 in feedback:\n%s", res.OverallFeedback)
	}
	if !strings.Contains(res.OverallFeedback, "**Pronunciation**") {
		t.Errorf("timed-out criterion missing from feedback entirely:\n%s", res.OverallFeedback)
	}
}

// TestSwarm_CallbackDoesNotSerialiseAgents proves the callback is invoked
// outside the results mutex. A blocking callback must not stop other agents
// from recording their own results -- otherwise one slow WebSocket consumer
// stalls the whole swarm.
func TestSwarm_CallbackDoesNotSerialiseAgents(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	release := make(chan struct{})
	entered := make(chan string, 4)

	done := make(chan struct{})
	go func() {
		defer close(done)
		_, _ = EvaluateSwarm(ctx, &FailingCriteriaMock{}, "Prompt", "Type", "Transcript",
			func(ev CriterionEvent) {
				entered <- ev.Criterion
				<-release // every callback blocks until the test says otherwise
			})
	}()

	// All four agents must reach their callback even though none can leave it.
	// If onCriterion were called under the mutex, only one would get here.
	for i := 0; i < 4; i++ {
		select {
		case <-entered:
		case <-time.After(3 * time.Second):
			t.Fatalf("only %d of 4 agents reached the callback; it is serialising them", i)
		}
	}
	close(release)

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("EvaluateSwarm did not return after callbacks were released")
	}
}
