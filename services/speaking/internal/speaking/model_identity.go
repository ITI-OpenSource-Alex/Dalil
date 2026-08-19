package speaking

import (
	"os"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
)

// SPEAK-EVAL-003 — model identity for provenance.
//
// The Langfuse generation span on the practice path carried a hardcoded
// "claude-3-5-haiku-20241022". cmd/speaking/main.go builds two LLM clients from
// configuration, a practice model and an exam model, and neither has been Haiku
// for a long time. So every generation in the dashboard was attributed to a
// model that never ran, and the exam path attributed its generations to no model
// at all.
//
// That is not a cosmetic telemetry bug. Cost-per-model, latency-per-model and
// any "did the upgrade help" comparison were all computed over a constant, which
// is the same failure mode as BUG-055 wearing different clothes: a field that
// looks like a measurement and is actually a literal.

// modelIdentifier is implemented by *llm.Client.
//
// An optional interface rather than a widened agents.LLMClient: that interface
// is deliberately one method, and every test in this package injects a mock
// through it. Requiring Model() there would force a dozen mocks to grow a method
// whose value they would have to invent.
type modelIdentifier interface {
	Model() string
}

// unknownModel is what provenance records when the caller cannot say which model
// ran -- a test mock, or a client that predates the accessor.
//
// It is deliberately not a plausible model id. A wrong-but-plausible default is
// worse than an obviously missing value, because it is the kind of thing a
// dashboard will happily average.
const unknownModel = "unknown"

// EffectiveLLMModel reports the model the given client actually calls with.
func EffectiveLLMModel(client agents.LLMClient) string {
	identifier, ok := client.(modelIdentifier)
	if !ok {
		return unknownModel
	}
	if model := identifier.Model(); model != "" {
		return model
	}
	return unknownModel
}

// scorerVersion identifies the build that produced an explanation.
//
// Two explanations for the same band are only comparable if this matches. Read
// from the environment so a container records its own image tag rather than a
// constant that drifts from whatever is deployed.
func scorerVersion() string {
	if v := os.Getenv("GOA_SCORER_VERSION"); v != "" {
		return v
	}
	return "speaking@dev"
}
