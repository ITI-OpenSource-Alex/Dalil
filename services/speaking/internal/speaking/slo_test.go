package speaking

import (
	"strings"
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestPCMDurationMs(t *testing.T) {
	tests := []struct {
		name  string
		bytes int
		want  int64
	}{
		// 16kHz * 2 bytes * 1 channel = 32 bytes per millisecond.
		{"one second", 32000, 1000},
		{"35 seconds (the GOA-098 clip)", 35 * 32000, 35000},
		{"sub-millisecond", 16, 0},
		{"zero", 0, 0},
		// Negative can only arrive via a caller bug, but the guard exists so the
		// ratio below it can never divide by a negative and record a nonsense
		// observation that cannot be removed from the histogram.
		{"negative", -1, 0},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := pcmDurationMs(tt.bytes); got != tt.want {
				t.Errorf("pcmDurationMs(%d) = %d, want %d", tt.bytes, got, tt.want)
			}
		})
	}
}

// TestCheckSLO_IncrementsLabelledCounter is the acceptance criterion: a breach
// must increment goa_speaking_slo_violations_total with the CORRECT label. The
// label value is asserted explicitly -- a typo'd label does not error, it
// silently creates a series no alert matches.
func TestCheckSLO_IncrementsLabelledCounter(t *testing.T) {
	tests := []struct {
		name     string
		budget   sloBudget
		observed float64
		want     bool
	}{
		{"transcription ratio breach", budgetTranscriptionRatio, 0.9, true},
		{"transcription ratio within budget", budgetTranscriptionRatio, 0.33, false},
		// 0.480 was the worst ratio measured against the real sidecar, on a 15s
		// Part 1 answer. It must NOT breach -- that is the whole reason the
		// budget moved off 0.5.
		{"worst measured real ratio stays within budget", budgetTranscriptionRatio, 0.480, false},
		{"transcription ratio exactly at limit", budgetTranscriptionRatio, 0.6, false},
		{"first criterion breach", budgetFirstCriterion, 60000, true},
		// 23.4s is the measured STT floor on a 68s Part 2 answer. A budget that
		// breaches before a single agent has had a chance to answer is a budget
		// nobody can act on.
		{"measured STT floor alone does not breach", budgetFirstCriterion, 23400, false},
		{"first criterion within budget", budgetFirstCriterion, 12000, false},
		{"e2e breach", budgetE2E, 120000, true},
		{"e2e within budget", budgetE2E, 77000, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := &Client{id: "session-1", userID: "user-1", correlationID: "corr-1"}
			before := testutil.ToFloat64(sloViolationsMetric.WithLabelValues(tt.budget.label))

			got := c.checkSLO(tt.budget, tt.observed)
			if got != tt.want {
				t.Errorf("checkSLO(%v, %v) = %v, want %v", tt.budget.label, tt.observed, got, tt.want)
			}

			after := testutil.ToFloat64(sloViolationsMetric.WithLabelValues(tt.budget.label))
			wantDelta := 0.0
			if tt.want {
				wantDelta = 1.0
			}
			if after-before != wantDelta {
				t.Errorf("counter{budget=%q} moved by %v, want %v", tt.budget.label, after-before, wantDelta)
			}
		})
	}
}

// TestSLOBudgetLabelsAreDistinct guards the reason the counter is labelled at
// all: a single unlabelled counter cannot distinguish a slow provider from a
// slow sidecar. Two budgets sharing a label would silently collapse them.
func TestSLOBudgetLabelsAreDistinct(t *testing.T) {
	labels := map[string]bool{}
	for _, b := range []sloBudget{budgetTranscriptionRatio, budgetFirstCriterion, budgetE2E} {
		if b.label == "" {
			t.Fatal("a budget has an empty label")
		}
		if labels[b.label] {
			t.Errorf("duplicate budget label %q", b.label)
		}
		labels[b.label] = true
	}
}

func TestSanitizeCorrelationID(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"gateway uuid", "3f2b1c9e-8a4d-4f21-9b77-1c2d3e4f5a6b", "3f2b1c9e-8a4d-4f21-9b77-1c2d3e4f5a6b"},
		{"underscore token", "req_12345", "req_12345"},
		{"empty", "", ""},
		// Rejected rather than truncated: a mangled id correlates a session to
		// the wrong request, which is worse than having no id at all.
		{"too long", strings.Repeat("a", 65), ""},
		{"newline injection", "abc\ndef", ""},
		{"json injection", `abc","level":"fatal`, ""},
		{"space", "abc def", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := sanitizeCorrelationID(tt.in); got != tt.want {
				t.Errorf("sanitizeCorrelationID(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}
