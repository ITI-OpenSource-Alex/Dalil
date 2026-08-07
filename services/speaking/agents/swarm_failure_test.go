package agents

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

type erroringLLMClient struct{ err error }

func (m *erroringLLMClient) StreamCompletion(ctx context.Context, systemPrompt, userPrompt string) (llm.CompletionResult, error) {
	return llm.CompletionResult{}, m.err
}

// TestSwarm_ProviderErrorIsCapturedNotSwallowed. The error used to be dropped
// on the floor, so an expired credential and a genuinely slow provider produced
// identical output and diagnosing which one you had meant curling the provider
// by hand. That actually happened during the GOA-032 re-measurement.
func TestSwarm_ProviderErrorIsCapturedNotSwallowed(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	res, err := EvaluateSwarm(ctx,
		&erroringLLMClient{err: errors.New(`anthropic stream failed: 401 {"type":"authentication_error"}`)},
		"Prompt", "Type", "Transcript", nil)
	if err == nil {
		t.Fatal("expected an error when every agent fails")
	}
	if res.Status != "failed" {
		t.Errorf("status = %q, want failed", res.Status)
	}

	for _, name := range CriterionOrder {
		dim := res.Dimensions[name]
		if dim.Error == "" {
			t.Errorf("criterion %q carries no error breadcrumb", name)
		}
		if dim.Error == AgentErrorDeadline {
			t.Errorf("criterion %q reported a deadline; it was a provider error", name)
		}
		if !strings.Contains(dim.Error, "authentication_error") {
			t.Errorf("criterion %q breadcrumb lost the cause: %q", name, dim.Error)
		}
	}
}

// TestSwarm_DeadlineIsDistinguishableFromProviderError is the distinction the
// whole breadcrumb exists for.
func TestSwarm_DeadlineIsDistinguishableFromProviderError(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()

	res, _ := EvaluateSwarm(ctx,
		&SelectiveDelayMockClient{DelayCriteria: "", DelayDuration: 2 * time.Second},
		"Prompt", "Type", "Transcript", nil)

	for _, name := range CriterionOrder {
		if got := res.Dimensions[name].Error; got != AgentErrorDeadline {
			t.Errorf("criterion %q error = %q, want %q", name, got, AgentErrorDeadline)
		}
	}
}

// TestSwarm_ErrorBreadcrumbNeverReachesTheWire. Dimensions is serialised
// wholesale into the client's evaluation frame AND into the persisted
// evaluation JSONB, so a tagged Error field would ship raw provider text to
// every browser and store it indefinitely.
func TestSwarm_ErrorBreadcrumbNeverReachesTheWire(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	const secretish = "internal-host-9f2a.example.invalid"
	res, _ := EvaluateSwarm(ctx,
		&erroringLLMClient{err: errors.New("dial tcp " + secretish + ": refused")},
		"Prompt", "Type", "Transcript", nil)

	// It is present in the Go value, for logs and metrics.
	if res.Dimensions[CriterionOrder[0]].Error == "" {
		t.Fatal("breadcrumb missing from the in-process value")
	}

	// And absent once serialised.
	blob, err := json.Marshal(res)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if strings.Contains(string(blob), secretish) {
		t.Errorf("provider error text leaked to the wire:\n%s", blob)
	}
	if strings.Contains(string(blob), `"error"`) {
		t.Errorf("an error field was serialised into the payload:\n%s", blob)
	}
}

// TestErrorSummary_IsBounded keeps a verbose provider failure from filling the
// log line (and, before json:"-", the response).
func TestErrorSummary_IsBounded(t *testing.T) {
	if got := errorSummary(nil); got != "" {
		t.Errorf("errorSummary(nil) = %q, want empty", got)
	}
	long := errors.New(strings.Repeat("x", 5000))
	got := errorSummary(long)
	if len(got) > maxAgentErrorChars+3 {
		t.Errorf("errorSummary returned %d chars, want <= %d", len(got), maxAgentErrorChars+3)
	}
	if !strings.HasSuffix(got, "...") {
		t.Errorf("a truncated summary should say so, got %q", got[len(got)-10:])
	}
}
