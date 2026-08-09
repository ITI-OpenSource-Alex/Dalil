package speaking

import (
	"context"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

// A client that knows its model, matching *llm.Client's shape.
type modelAwareClient struct {
	model string
}

func (m modelAwareClient) StreamCompletion(context.Context, string, string) (llm.CompletionResult, error) {
	return llm.CompletionResult{}, nil
}

func (m modelAwareClient) Model() string { return m.model }

// A client that does not, matching the mocks every other test here injects.
type modelBlindClient struct{}

func (modelBlindClient) StreamCompletion(context.Context, string, string) (llm.CompletionResult, error) {
	return llm.CompletionResult{}, nil
}

func TestEffectiveLLMModelReadsTheClientNotALiteral(t *testing.T) {
	cases := []struct {
		name   string
		client agents.LLMClient
		want   string
	}{
		{"configured practice model", modelAwareClient{model: "claude-opus-5"}, "claude-opus-5"},
		{"configured exam model", modelAwareClient{model: "claude-opus-5"}, "claude-opus-5"},
		// The failure modes report "unknown" rather than a plausible id. A
		// dashboard will average a plausible default without complaint; it cannot
		// average "unknown".
		{"client with an empty model", modelAwareClient{model: ""}, unknownModel},
		{"client that cannot report a model", modelBlindClient{}, unknownModel},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := EffectiveLLMModel(tc.client); got != tc.want {
				t.Errorf("EffectiveLLMModel() = %q, want %q", got, tc.want)
			}
		})
	}
}

// The real client must satisfy the optional interface. Without this the accessor
// could be deleted or renamed and every span would quietly fall back to
// "unknown" -- a regression with no failing test and no visible symptom outside
// the Langfuse dashboard.
func TestRealLLMClientReportsItsModel(t *testing.T) {
	client := llm.NewClient("claude-opus-5", "test-key", "https://example.invalid")

	var asAgent agents.LLMClient = client
	if got := EffectiveLLMModel(asAgent); got != "claude-opus-5" {
		t.Errorf("EffectiveLLMModel(*llm.Client) = %q, want the configured model", got)
	}
}
