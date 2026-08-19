package agents

import (
	"context"
	"math"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

func words(spec ...[3]float64) []Word {
	// [start, end, probability]
	out := make([]Word, 0, len(spec))
	for i, s := range spec {
		out = append(out, Word{
			Word:        "w",
			Start:       s[0],
			End:         s[1],
			Probability: s[2],
		})
		_ = i
	}
	return out
}

func TestComputeProsodyFromWords(t *testing.T) {
	tests := []struct {
		name      string
		words     []Word
		duration  float64
		wantOK    bool
		wantWPM   float64
		wantPause int
		wantLong  int
	}{
		{
			name:     "no words is not measurable",
			words:    nil,
			duration: 30,
			wantOK:   false,
		},
		{
			name:     "zero duration is not measurable",
			words:    words([3]float64{0, 0.5, 0.9}),
			duration: 0,
			wantOK:   false,
		},
		{
			name:      "continuous speech has no pauses",
			words:     words([3]float64{0, 0.5, 0.9}, [3]float64{0.5, 1.0, 0.9}, [3]float64{1.0, 1.5, 0.9}),
			duration:  60,
			wantOK:    true,
			wantWPM:   3,
			wantPause: 0,
			wantLong:  0,
		},
		{
			name: "one long pause counts once in both buckets",
			words: words(
				[3]float64{0, 0.5, 0.9},
				[3]float64{3.0, 3.5, 0.9}, // 2.5s gap
			),
			duration:  60,
			wantOK:    true,
			wantWPM:   2,
			wantPause: 1,
			wantLong:  1,
		},
		{
			name: "a short pause is not a long one",
			words: words(
				[3]float64{0, 0.5, 0.9},
				[3]float64{1.0, 1.5, 0.9}, // 0.5s gap
			),
			duration:  60,
			wantOK:    true,
			wantWPM:   2,
			wantPause: 1,
			wantLong:  0,
		},
		{
			name:      "single word is measurable and has no gaps",
			words:     words([3]float64{0, 0.5, 0.9}),
			duration:  60,
			wantOK:    true,
			wantWPM:   1,
			wantPause: 0,
			wantLong:  0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			f, ok := ComputeProsody(tt.words, tt.duration)
			if ok != tt.wantOK {
				t.Fatalf("ok = %v, want %v", ok, tt.wantOK)
			}
			if !ok {
				return
			}
			if math.Abs(f.WordsPerMinute-tt.wantWPM) > 0.01 {
				t.Errorf("WordsPerMinute = %v, want %v", f.WordsPerMinute, tt.wantWPM)
			}
			if f.PauseCount != tt.wantPause {
				t.Errorf("PauseCount = %d, want %d", f.PauseCount, tt.wantPause)
			}
			if f.LongPauseCount != tt.wantLong {
				t.Errorf("LongPauseCount = %d, want %d", f.LongPauseCount, tt.wantLong)
			}
		})
	}
}

// TestPauseThresholdBoundaries — a gap of exactly the threshold must land on the
// documented side of it, in both directions.
func TestPauseThresholdBoundaries(t *testing.T) {
	exactlyPause := words([3]float64{0, 1.0, 0.9}, [3]float64{1.0 + pauseThresholdS, 2.0, 0.9})
	f, ok := ComputeProsody(exactlyPause, 60)
	if !ok || f.PauseCount != 1 {
		t.Errorf("a gap of exactly %.1fs must count as a pause, got %d", pauseThresholdS, f.PauseCount)
	}
	if f.LongPauseCount != 0 {
		t.Errorf("a %.1fs gap is not a long pause", pauseThresholdS)
	}

	exactlyLong := words([3]float64{0, 1.0, 0.9}, [3]float64{1.0 + longPauseThresholdS, 2.0, 0.9})
	f, _ = ComputeProsody(exactlyLong, 60)
	if f.LongPauseCount != 1 {
		t.Errorf("a gap of exactly %.1fs must count as a long pause", longPauseThresholdS)
	}

	justUnder := words([3]float64{0, 1.0, 0.9}, [3]float64{1.0 + pauseThresholdS - 0.01, 2.0, 0.9})
	f, _ = ComputeProsody(justUnder, 60)
	if f.PauseCount != 0 {
		t.Errorf("a gap just under %.1fs is not a pause", pauseThresholdS)
	}
}

// TestArticulationRateExcludesPauses — the metric that separates "speaks slowly"
// from "speaks normally but pauses a lot". Both give the same WPM.
func TestArticulationRateExcludesPauses(t *testing.T) {
	// 100 words in 60s, of which 30s is one enormous pause.
	w := make([]Word, 0, 100)
	for i := 0; i < 50; i++ {
		start := float64(i) * 0.3
		w = append(w, Word{Word: "w", Start: start, End: start + 0.29, Probability: 0.9})
	}
	// A 30s silence, then the remaining 50 words.
	for i := 0; i < 50; i++ {
		start := 45.0 + float64(i)*0.3
		w = append(w, Word{Word: "w", Start: start, End: start + 0.29, Probability: 0.9})
	}

	f, ok := ComputeProsody(w, 60)
	if !ok {
		t.Fatal("expected measurable features")
	}
	if math.Abs(f.WordsPerMinute-100) > 0.5 {
		t.Errorf("WordsPerMinute = %v, want ~100", f.WordsPerMinute)
	}
	if f.ArticulationRate <= f.WordsPerMinute {
		t.Errorf(
			"ArticulationRate (%v) must exceed WordsPerMinute (%v) when a third of "+
				"the clip is silence; otherwise the two metrics carry the same "+
				"information and neither distinguishes slow speech from pausing",
			f.ArticulationRate, f.WordsPerMinute,
		)
	}
	if f.LongPauseCount != 1 {
		t.Errorf("LongPauseCount = %d, want 1", f.LongPauseCount)
	}
	if f.PauseRatio < 0.4 {
		t.Errorf("PauseRatio = %v, want >= 0.4", f.PauseRatio)
	}
}

func TestConfidenceAggregation(t *testing.T) {
	f, ok := ComputeProsody(words(
		[3]float64{0, 0.5, 1.0},
		[3]float64{0.5, 1.0, 0.5},
		[3]float64{1.0, 1.5, 0.3},
		[3]float64{1.5, 2.0, 0.2},
	), 60)
	if !ok {
		t.Fatal("expected measurable features")
	}
	if math.Abs(f.MeanWordConfidence-0.5) > 0.001 {
		t.Errorf("MeanWordConfidence = %v, want 0.5", f.MeanWordConfidence)
	}
	// 0.3 and 0.2 are below the 0.5 threshold; 0.5 itself is not.
	if math.Abs(f.LowConfidenceWordRatio-0.5) > 0.001 {
		t.Errorf("LowConfidenceWordRatio = %v, want 0.5", f.LowConfidenceWordRatio)
	}
}

// TestUnmeasurableInputIsNeverPresentedAsZero — the BUG-055 shape applied to
// prosody. The contract is that callers key off `ok` and omit the block; this
// test pins the two inputs that must produce ok=false, since a zeroed block
// ("0 words per minute, 0 pauses") describes a candidate who said nothing.
func TestUnmeasurableInputIsNeverPresentedAsZero(t *testing.T) {
	for _, tc := range []struct {
		name     string
		words    []Word
		duration float64
	}{
		{"no words at all", nil, 30},
		{"no duration", words([3]float64{0, 0.5, 0.9}), 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if _, ok := ComputeProsody(tc.words, tc.duration); ok {
				t.Fatal("reported as measurable; callers would render a zeroed block")
			}
		})
	}
}

func TestRenderContainsTheMeasurements(t *testing.T) {
	f, ok := ComputeProsody(words(
		[3]float64{0, 0.5, 0.95},
		[3]float64{2.0, 2.5, 0.95},
	), 60)
	if !ok {
		t.Fatal("expected measurable features")
	}
	rendered := f.Render()
	for _, want := range []string{
		"MEASURED SPEECH FEATURES",
		"words per minute",
		"articulation rate",
		"longest",
		"confidence",
	} {
		if !strings.Contains(rendered, want) {
			t.Errorf("rendered block is missing %q:\n%s", want, rendered)
		}
	}
}

// --- prompt wiring --------------------------------------------------------

// recordingClient captures the prompts each agent actually receives.
//
// The mutex is load-bearing: all four agents run concurrently and call this from
// their own goroutines, so an unguarded map write is a genuine race. Caught by
// `go test -race` on the first run of this file.
type recordingClient struct {
	mu      sync.Mutex
	prompts map[string]string
}

func (r *recordingClient) StreamCompletion(_ context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	r.mu.Lock()
	if r.prompts == nil {
		r.prompts = map[string]string{}
	}
	r.prompts[criterionFromSystemPrompt(systemPrompt)] = userPrompt
	r.mu.Unlock()
	return llm.CompletionResult{
		Text: `{"band": 7.0, "feedback": "ok", "examples": [], "overall_feedback": "ok", "part_notes": {}, "improvement_tip": "t"}`,
	}, nil
}

// snapshot returns a copy so assertions never read the map while an agent that
// outlived the swarm deadline is still writing to it.
func (r *recordingClient) snapshot() map[string]string {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make(map[string]string, len(r.prompts))
	for k, v := range r.prompts {
		out[k] = v
	}
	return out
}

func sampleFeatures(t *testing.T) *ProsodyFeatures {
	t.Helper()
	f, ok := ComputeProsody(words(
		[3]float64{0, 0.5, 0.9},
		[3]float64{2.0, 2.5, 0.9},
		[3]float64{2.6, 3.1, 0.9},
	), 30)
	if !ok {
		t.Fatal("fixture features are not measurable")
	}
	return &f
}

// TestOnlyAcousticCriteriaReceiveFeatures — Lexical and Grammar have no use for
// the block and it is pure token cost on every call.
func TestOnlyAcousticCriteriaReceiveFeatures(t *testing.T) {
	for _, tc := range []struct {
		name    string
		run     func(client LLMClient, f *ProsodyFeatures)
		wantFor map[string]bool
	}{
		{
			name: "streaming",
			run: func(client LLMClient, f *ProsodyFeatures) {
				ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
				defer cancel()
				_, _ = EvaluateSwarm(ctx, client, "q", "part2", "transcript", f, nil)
			},
		},
		{
			name: "holistic",
			run: func(client LLMClient, f *ProsodyFeatures) {
				ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
				defer cancel()
				_, _ = EvaluateHolisticSwarm(ctx, client, "transcript", f)
			},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			client := &recordingClient{}
			tc.run(client, sampleFeatures(t))
			prompts := client.snapshot()

			for _, criterion := range []string{"Fluency and Coherence", "Pronunciation"} {
				if !strings.Contains(prompts[criterion], "MEASURED SPEECH FEATURES") {
					t.Errorf("%s did not receive the feature block; it is graded on acoustics", criterion)
				}
			}
			for _, criterion := range []string{"Lexical Resource", "Grammatical Range and Accuracy"} {
				if strings.Contains(prompts[criterion], "MEASURED SPEECH FEATURES") {
					t.Errorf("%s received the feature block; it has no use for it and pays for the tokens", criterion)
				}
			}
		})
	}
}

// TestNilFeaturesRendersNoBlock — never zeros.
func TestNilFeaturesRendersNoBlock(t *testing.T) {
	client := &recordingClient{}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_, _ = EvaluateSwarm(ctx, client, "q", "part2", "transcript", nil, nil)

	for criterion, prompt := range client.snapshot() {
		if strings.Contains(prompt, "MEASURED SPEECH FEATURES") {
			t.Errorf("%s got a feature block from nil features", criterion)
		}
		if strings.Contains(prompt, "0 words per minute") {
			t.Errorf(
				"%s got a zeroed feature block. That describes a candidate who said "+
					"nothing, and is a worse lie than omitting it (BUG-055 shape).",
				criterion,
			)
		}
	}
}

// TestPronunciationPromptDoesNotClaimPhonology is the test that fails if the old
// prompt is restored by a merge.
func TestPronunciationPromptDoesNotClaimPhonology(t *testing.T) {
	for name, prompt := range map[string]string{
		"streaming": PronunciationSystemPrompt,
		"holistic":  HolisticPronunciationSystemPrompt,
	} {
		if strings.Contains(prompt, "as indicated by written speech tokens") {
			t.Errorf(
				"%s Pronunciation prompt still claims to read phonology from orthography; "+
					"spelling carries no information about how a candidate sounded",
				name,
			)
		}
		if !strings.Contains(prompt, "You have NOT heard the audio") {
			t.Errorf("%s Pronunciation prompt must state its own limits explicitly", name)
		}
	}
}

func TestFluencyPromptDirectsRateJudgementAtTheMeasurements(t *testing.T) {
	for name, prompt := range map[string]string{
		"streaming": FluencySystemPrompt,
		"holistic":  HolisticFluencySystemPrompt,
	} {
		if !strings.Contains(prompt, "MEASURED") {
			t.Errorf("%s Fluency prompt does not mention the measured features", name)
		}
	}
}
