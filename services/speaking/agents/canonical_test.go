package agents

import (
	"fmt"
	"math"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
)

// SPEAK-EVAL-003 acceptance: "equivalent practice/exam canonical input returns
// equivalent criterion bands/calculation under a deterministic scorer".
//
// The existing TestSwarmAndHolisticAgreeOnBandContract drives both paths through
// a fault matrix and checks the two wire shapes agree on the aggregate. These
// tests check the stronger property the contract needs: that both reduce to the
// SAME canonical evaluation, criterion by criterion, reason by reason. Agreeing
// on a single number is not the same as agreeing on what happened.

// outcome is one agent's terminal state, expressed the way both paths express
// it. Building both source structs from one matrix is the point: if the fixture
// for practice and the fixture for exam were written separately, the test would
// prove only that two hand-written fixtures match.
type outcome struct {
	band     float64
	timedOut bool
	errMsg   string
}

func swarmFrom(m map[string]outcome) SwarmResult {
	dims := make(map[string]AgentResult, len(m))
	for name, o := range m {
		dims[name] = AgentResult{
			Criterion: name,
			Band:      o.band,
			Feedback:  "summary for " + name,
			TimedOut:  o.timedOut,
			Error:     o.errMsg,
		}
	}
	return SwarmResult{Dimensions: dims}
}

func holisticFrom(m map[string]outcome) HolisticSwarmResult {
	dims := make(map[string]HolisticAgentResult, len(m))
	for name, o := range m {
		dims[name] = HolisticAgentResult{
			Criterion:       name,
			Band:            o.band,
			OverallFeedback: "summary for " + name,
			TimedOut:        o.timedOut,
			Error:           o.errMsg,
		}
	}
	return HolisticSwarmResult{Dimensions: dims}
}

func testMeta(mode contract.Mode) CanonicalMeta {
	return CanonicalMeta{
		EvaluationID:  "eval-test",
		Mode:          mode,
		CreatedAt:     time.Date(2026, 8, 8, 12, 0, 0, 0, time.UTC),
		ScorerVersion: "speaking@test",
		LLMProvider:   "agentrouter",
		LLMModel:      "claude-opus-4-8",
	}
}

// faultMatrix enumerates the ways the four agents can land. Every combination of
// scored and each failure mode would be 4^4; these are the cases that exercise
// a distinct branch of the scorer.
func faultMatrix() []struct {
	name string
	in   map[string]outcome
} {
	all := func(o ...outcome) map[string]outcome {
		m := make(map[string]outcome, 4)
		for i, name := range CriterionOrder {
			m[name] = o[i]
		}
		return m
	}
	ok := func(b float64) outcome { return outcome{band: b} }
	deadline := outcome{timedOut: true, errMsg: AgentErrorDeadline}
	provider := outcome{timedOut: true, errMsg: "401 invalid api key"}
	malformed := outcome{timedOut: true, errMsg: "failed to parse JSON from LLM: unexpected end of input"}

	return []struct {
		name string
		in   map[string]outcome
	}{
		{"all four scored", all(ok(6.5), ok(6.0), ok(7.0), ok(6.5))},
		{"three scored one deadline", all(ok(6.5), ok(6.0), ok(7.0), deadline)},
		{"three scored one provider error", all(ok(7.0), ok(7.0), ok(6.5), provider)},
		{"three scored one malformed", all(ok(5.0), ok(5.5), ok(5.0), malformed)},
		{"two scored two failed", all(ok(8.0), ok(8.0), deadline, provider)},
		{"one scored three failed", all(ok(9.0), deadline, deadline, provider)},
		{"none scored", all(deadline, provider, malformed, deadline)},
		// A genuine band 0: the candidate said nothing usable. It must be scored,
		// not swallowed as unavailable, which is the mirror image of BUG-055.
		{"a real band zero is a score", all(ok(0), ok(0), ok(0), ok(0))},
		{"mixed halves round up", all(ok(6.5), ok(6.5), ok(6.5), ok(7.0))},
		{"mixed halves round down", all(ok(6.0), ok(6.0), ok(6.0), ok(6.5))},
	}
}

func TestPracticeAndExamProduceTheSameCanonicalEvaluation(t *testing.T) {
	for _, tc := range faultMatrix() {
		t.Run(tc.name, func(t *testing.T) {
			practice := CanonicalizeSwarm(swarmFrom(tc.in), testMeta(contract.ModePractice))
			exam := CanonicalizeHolistic(holisticFrom(tc.in), testMeta(contract.ModeExam))

			if len(practice.Criteria) != len(exam.Criteria) {
				t.Fatalf("criterion count differs: practice %d, exam %d",
					len(practice.Criteria), len(exam.Criteria))
			}

			for i := range practice.Criteria {
				p, e := practice.Criteria[i], exam.Criteria[i]
				if p.CriterionID != e.CriterionID {
					t.Errorf("criterion %d: id practice=%s exam=%s", i, p.CriterionID, e.CriterionID)
				}
				if p.Status != e.Status {
					t.Errorf("%s: status practice=%s exam=%s", p.CriterionID, p.Status, e.Status)
				}
				if p.UnavailableReason != e.UnavailableReason {
					t.Errorf("%s: reason practice=%q exam=%q",
						p.CriterionID, p.UnavailableReason, e.UnavailableReason)
				}
				if !bandsEqual(p.Band, e.Band) {
					t.Errorf("%s: band practice=%s exam=%s",
						p.CriterionID, bandString(p.Band), bandString(e.Band))
				}
			}

			// The calculation, not just the criteria.
			if !bandsEqual(practice.Overall.Band, exam.Overall.Band) {
				t.Errorf("overall band: practice=%s exam=%s",
					bandString(practice.Overall.Band), bandString(exam.Overall.Band))
			}
			if !bandsEqual(practice.Overall.UnroundedMean, exam.Overall.UnroundedMean) {
				t.Errorf("unrounded mean: practice=%s exam=%s",
					bandString(practice.Overall.UnroundedMean), bandString(exam.Overall.UnroundedMean))
			}
			if practice.Status != exam.Status {
				t.Errorf("status: practice=%s exam=%s", practice.Status, exam.Status)
			}
			if practice.Overall.MinCriteriaRequired != exam.Overall.MinCriteriaRequired {
				t.Errorf("threshold: practice=%d exam=%d",
					practice.Overall.MinCriteriaRequired, exam.Overall.MinCriteriaRequired)
			}
			if practice.Overall.RoundingRule != exam.Overall.RoundingRule {
				t.Errorf("rounding rule: practice=%q exam=%q",
					practice.Overall.RoundingRule, exam.Overall.RoundingRule)
			}
		})
	}
}

// A timed-out criterion must be absent, not zero. This is the defect that made
// the swarm report a band the model never produced.
func TestTimeoutsAreUnavailableNeverBandZero(t *testing.T) {
	for _, tc := range faultMatrix() {
		t.Run(tc.name, func(t *testing.T) {
			eval := CanonicalizeSwarm(swarmFrom(tc.in), testMeta(contract.ModePractice))
			for _, c := range eval.Criteria {
				o := tc.in[displayNameFor(t, c.CriterionID)]
				if !o.timedOut {
					continue
				}
				if c.Status != contract.CriterionUnavailable {
					t.Errorf("%s: timed out but status is %s", c.CriterionID, c.Status)
				}
				if c.Band != nil {
					t.Errorf("%s: timed out but carries band %.1f -- band 0.0 is a real "+
						"IELTS value and must never mean \"not measured\"", c.CriterionID, *c.Band)
				}
				if c.UnavailableReason == "" {
					t.Errorf("%s: unavailable with no reason", c.CriterionID)
				}
			}
		})
	}
}

// The breadcrumb must survive into a reason a caller can act on. A deadline may
// succeed on retry; an invalid credential will not.
func TestFailureModesMapToDistinctReasons(t *testing.T) {
	cases := []struct {
		errMsg string
		want   contract.UnavailableReason
	}{
		{AgentErrorDeadline, contract.ReasonDeadlineExceeded},
		{"401 invalid api key", contract.ReasonProviderError},
		{"failed to parse JSON from LLM: unexpected end of input", contract.ReasonInvalidOutput},
		{"", contract.ReasonProviderError},
	}
	for _, tc := range cases {
		t.Run(string(tc.want), func(t *testing.T) {
			status, band, reason := classifyOutcome(0, true, tc.errMsg)
			if status != contract.CriterionUnavailable {
				t.Errorf("status = %s, want unavailable", status)
			}
			if band != nil {
				t.Errorf("band = %.1f, want absent", *band)
			}
			if reason != tc.want {
				t.Errorf("reason = %q, want %q", reason, tc.want)
			}
		})
	}
}

// Below the threshold, no overall band at all -- not a band averaged from the
// one or two agents that happened to survive (BUG-040).
func TestOverallBandIsWithheldBelowThreshold(t *testing.T) {
	for _, tc := range faultMatrix() {
		t.Run(tc.name, func(t *testing.T) {
			eval := CanonicalizeSwarm(swarmFrom(tc.in), testMeta(contract.ModePractice))

			scored := 0
			for _, c := range eval.Criteria {
				if c.Scored() {
					scored++
				}
			}

			if scored < MinCriteriaForOverallBand {
				if eval.Overall.Band != nil {
					t.Errorf("%d criteria scored (threshold %d) but an overall band of %.1f "+
						"was published", scored, MinCriteriaForOverallBand, *eval.Overall.Band)
				}
				if eval.Overall.UnroundedMean != nil {
					t.Errorf("mean published below threshold: %.4f", *eval.Overall.UnroundedMean)
				}
				return
			}

			if eval.Overall.Band == nil {
				t.Fatalf("%d criteria scored (threshold %d) but no overall band was computed",
					scored, MinCriteriaForOverallBand)
			}
			// The published band must follow arithmetically from the criteria that
			// were actually included -- recomputed here rather than trusted.
			sum := 0.0
			for _, id := range eval.Overall.IncludedCriteria {
				for _, c := range eval.Criteria {
					if c.CriterionID == id && c.Band != nil {
						sum += *c.Band
					}
				}
			}
			wantMean := sum / float64(len(eval.Overall.IncludedCriteria))
			if math.Abs(*eval.Overall.UnroundedMean-wantMean) > 1e-9 {
				t.Errorf("unrounded mean = %.6f, recomputed %.6f", *eval.Overall.UnroundedMean, wantMean)
			}
			if want := RoundIELTSBand(wantMean); *eval.Overall.Band != want {
				t.Errorf("overall band = %.1f, want %.1f from mean %.4f", *eval.Overall.Band, want, wantMean)
			}
		})
	}
}

// Whatever the fault pattern, the canonical output must satisfy the contract's
// own validator. A canonicaliser that produces an invalid evaluation is worse
// than no canonicaliser: it launders a broken result through a type that claims
// to be checked.
func TestCanonicalOutputSatisfiesTheContract(t *testing.T) {
	for _, tc := range faultMatrix() {
		t.Run(tc.name, func(t *testing.T) {
			for _, eval := range []contract.Evaluation{
				CanonicalizeSwarm(swarmFrom(tc.in), testMeta(contract.ModePractice)),
				CanonicalizeHolistic(holisticFrom(tc.in), testMeta(contract.ModeExam)),
			} {
				// No transcript and no descriptor citations are produced by this
				// adapter yet, so quote resolution has nothing to resolve; the
				// structural rules are what is under test here.
				for _, problem := range eval.Validate("", contract.AllowedDescriptorBands()) {
					t.Errorf("%s: %s", eval.Mode, problem.Error())
				}
			}
		})
	}
}

// Provenance must record what actually produced the score. An unexplainable
// band is the thing this contract exists to prevent.
func TestProvenanceRecordsTheRunNotADefault(t *testing.T) {
	meta := testMeta(contract.ModePractice)
	eval := CanonicalizeSwarm(swarmFrom(faultMatrix()[0].in), meta)

	if eval.Provenance.LLMModel != meta.LLMModel {
		t.Errorf("llm_model = %q, want the configured %q -- a hardcoded model id is how "+
			"the Langfuse span came to report Haiku while the service ran Opus",
			eval.Provenance.LLMModel, meta.LLMModel)
	}
	if eval.Provenance.RubricID != contract.RubricID {
		t.Errorf("rubric_id = %q, want %q", eval.Provenance.RubricID, contract.RubricID)
	}
	if eval.Provenance.RubricSHA256 != contract.RubricSHA256() {
		t.Error("rubric_sha256 does not match the frozen rubric")
	}
	if eval.Provenance.ScorerVersion == "" {
		t.Error("scorer_version is empty")
	}
	if eval.ScoreSemantics != contract.ScoreSemantics {
		t.Errorf("score_semantics = %q; this system must not claim to be a certified examiner",
			eval.ScoreSemantics)
	}
}

// The aggregate must not depend on the order the agents happened to finish in.
func TestAggregationIsOrderIndependent(t *testing.T) {
	bands := []float64{6.5, 6.0, 7.0, 5.5}
	first := aggregateBands(bands, 4)

	rotated := []float64{5.5, 6.5, 6.0, 7.0}
	second := aggregateBands(rotated, 4)

	if !bandsEqual(first.OverallBand, second.OverallBand) {
		t.Errorf("overall band depends on completion order: %s vs %s",
			bandString(first.OverallBand), bandString(second.OverallBand))
	}
	if !bandsEqual(first.UnroundedMean, second.UnroundedMean) {
		t.Errorf("mean depends on completion order: %s vs %s",
			bandString(first.UnroundedMean), bandString(second.UnroundedMean))
	}
}

func bandsEqual(a, b *float64) bool {
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	return math.Abs(*a-*b) < 1e-9
}

func bandString(b *float64) string {
	if b == nil {
		return "absent"
	}
	return fmt.Sprintf("%.4f", *b)
}

func displayNameFor(t *testing.T, id contract.CriterionID) string {
	t.Helper()
	for name, candidate := range canonicalCriterionID {
		if candidate == id {
			return name
		}
	}
	t.Fatalf("no display name for criterion %s", id)
	return ""
}
