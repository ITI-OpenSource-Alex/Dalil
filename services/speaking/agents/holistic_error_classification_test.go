package agents

// GOA-134 — error vs deadline classification on the holistic path.
//
// Split from holistic_contract_test.go because these assert on
// HolisticAgentResult.Error, which does not exist before this ticket: the
// errChan arm discarded the error entirely and set TimedOut=true for a provider
// failure. The band-contract matrix in that file compiles against the pre-fix
// code and captures the defect; this file asserts the new behaviour.

import (
	"context"
	"testing"
	"time"
)

// TestHolisticErrorIsNotReportedAsTimeout — swarm.go distinguishes these with a
// named constant and different log levels; holistic.go set TimedOut=true for
// both and discarded the error entirely.
func TestHolisticErrorIsNotReportedAsTimeout(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	client := &matrixMockClient{failCriteria: failFirstN(1), mode: failProviderError}
	res, _ := EvaluateHolisticSwarm(ctx, client, "transcript", nil)

	failed := res.Dimensions[CriterionOrder[0]]
	// TimedOut stays true for both causes -- it means "produced no score", and
	// swarm.go uses it the same way. Error is the discriminator, and asserting on
	// it is what stops a dead credential and a slow provider looking identical.
	if failed.Error == AgentErrorDeadline {
		t.Errorf("a provider error carries the deadline sentinel: %q", failed.Error)
	}
	if failed.Error == "" {
		t.Error("a failed criterion carries no error breadcrumb; a dead credential and a " +
			"slow provider are indistinguishable in the logs (GOA-032)")
	}
}

func TestHolisticDeadlineIsReportedAsTimeout(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	client := &matrixMockClient{failCriteria: failFirstN(1), mode: failDeadline}
	res, _ := EvaluateHolisticSwarm(ctx, client, "transcript", nil)

	failed := res.Dimensions[CriterionOrder[0]]
	if !failed.TimedOut {
		t.Error("a deadline was not reported as TimedOut")
	}
	if failed.Error != AgentErrorDeadline {
		t.Errorf("expected %q, got %q", AgentErrorDeadline, failed.Error)
	}
}

func TestHolisticParseFailureIsAnError(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	client := &matrixMockClient{failCriteria: failFirstN(1), mode: failParseError}
	res, _ := EvaluateHolisticSwarm(ctx, client, "transcript", nil)

	failed := res.Dimensions[CriterionOrder[0]]
	if failed.Error == AgentErrorDeadline {
		t.Error("a JSON parse failure carries the deadline sentinel (BUG-057's shape); " +
			"raising the timeout can never fix a malformed response")
	}
	if failed.Error == "" {
		t.Error("a parse failure carries no breadcrumb")
	}
}

