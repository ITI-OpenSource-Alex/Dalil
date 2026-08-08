package agents

import (
	"strings"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
)

// SPEAK-EVAL-003 — the canonical scorer core.
//
// Two execution paths produce a speaking score: EvaluateSwarm for practice and
// EvaluateHolisticSwarm for the full exam. They ran the same four criteria
// through the same rounding rule and the same completion threshold, in two
// copies of the arithmetic, held together by KEEP IN SYNC comments. That is not
// a synchronisation problem, it is a duplication problem: GOA-134 exists
// because one copy learned to distinguish a provider failure from a deadline
// and the other did not.
//
// So the arithmetic lives here once. Both paths call aggregateBands, and both
// convert to the same contract.Evaluation through the same classification
// function. The two wire shapes (SwarmResult, HolisticSwarmResult) are left
// alone deliberately: services/exam and the browser both read them, and
// reshaping a live contract is a separate, riskier change than removing the
// duplicated calculation behind it.

// canonicalCriterionID maps the display names used on the wire to the stable
// ids the contract uses.
//
// The display strings are what services/exam and the persisted JSONB have
// always keyed on, so they cannot simply be replaced. This map is the one place
// the two vocabularies meet.
var canonicalCriterionID = map[string]contract.CriterionID{
	"Fluency and Coherence":          contract.CriterionFluencyCoherence,
	"Lexical Resource":               contract.CriterionLexicalResource,
	"Grammatical Range and Accuracy": contract.CriterionGrammaticalRange,
	"Pronunciation":                  contract.CriterionPronunciation,
}

// CanonicalCriterionID resolves a wire criterion name. The bool is false for a
// name that is not one of the four, which callers must not silently score.
func CanonicalCriterionID(name string) (contract.CriterionID, bool) {
	id, ok := canonicalCriterionID[name]
	return id, ok
}

// aggregateOutcome is what the deterministic scorer decides from a set of
// per-criterion outcomes. Nothing here is read off a model response.
type aggregateOutcome struct {
	// CompletedCount is how many criteria produced a real band.
	CompletedCount int
	// Partial is true when at least one criterion did not.
	Partial bool
	// OverallBand is nil below MinCriteriaForOverallBand. Nil, never 0.0: a
	// band of zero is a real IELTS value meaning the candidate said nothing
	// usable, and it must never stand in for "we did not compute this"
	// (BUG-055).
	OverallBand *float64
	// UnroundedMean is the mean before rounding, kept so an explanation can show
	// the arithmetic instead of asking the reader to trust it.
	UnroundedMean *float64
}

// aggregateBands is the deterministic scorer. One implementation, two callers.
//
// scored carries only the bands of criteria that actually produced one. A
// criterion that timed out contributes nothing -- not a zero. Averaging in a
// zero for an agent that never ran is BUG-055 expressed as arithmetic, and it
// drags a genuine band 7 candidate to 5.25 for reasons that have nothing to do
// with their English.
func aggregateBands(scored []float64, totalCriteria int) aggregateOutcome {
	out := aggregateOutcome{
		CompletedCount: len(scored),
		Partial:        len(scored) < totalCriteria,
	}
	if len(scored) == 0 {
		return out
	}

	// Below the threshold the mean describes which agents survived, not the
	// candidate (BUG-040), so neither the mean nor the band is published.
	if len(scored) < MinCriteriaForOverallBand {
		return out
	}

	sum := 0.0
	for _, b := range scored {
		sum += b
	}
	mean := sum / float64(len(scored))
	rounded := RoundIELTSBand(mean)

	out.UnroundedMean = &mean
	out.OverallBand = &rounded
	return out
}

// classifyOutcome decides whether one agent's outcome is a score or an absence,
// and why.
//
// This is the single place the "TimedOut" flag -- which despite its name means
// "produced no score" -- is translated into the contract's explicit status and
// reason. Both paths set that flag identically and both set an Error
// breadcrumb; the breadcrumb is what separates a dead credential from a slow
// provider, and raising the deadline only ever fixes one of them.
func classifyOutcome(band float64, timedOut bool, errMsg string) (contract.CriterionStatus, *float64, contract.UnavailableReason) {
	if !timedOut {
		b := band
		return contract.CriterionScored, &b, ""
	}

	switch {
	case errMsg == AgentErrorInsufficientEvidence:
		// Nothing failed. The input did not contain what this criterion
		// measures, and no retry changes that.
		return contract.CriterionUnavailable, nil, contract.ReasonInsufficientEvidence
	case errMsg == AgentErrorDeadline:
		return contract.CriterionUnavailable, nil, contract.ReasonDeadlineExceeded
	case strings.Contains(errMsg, "failed to parse JSON"):
		// BUG-057's shape: the provider answered, the answer was not usable.
		// Distinct from provider_error because retrying helps here and does not
		// help a dead credential.
		return contract.CriterionUnavailable, nil, contract.ReasonInvalidOutput
	default:
		return contract.CriterionUnavailable, nil, contract.ReasonProviderError
	}
}

// CanonicalMeta carries the facts the swarm itself does not know: which
// evaluation this is, which mode produced it, and the provenance of the run.
//
// It is a parameter rather than a package global because the effective model is
// read from configuration at call time. Hardcoding it is how the Langfuse span
// came to report a Haiku id while the service ran Opus, which made every
// model-to-model comparison in the telemetry meaningless.
type CanonicalMeta struct {
	EvaluationID  string
	Mode          contract.Mode
	CreatedAt     time.Time
	ScorerVersion string

	LLMProvider string
	LLMModel    string

	STTProvider      string
	STTModel         string
	AudioFormat      string
	TranscriptSHA256 string

	Measurements []contract.Measurement
}

// canonicalize builds the evaluation from already-classified criteria. Both
// public adapters funnel through it, so there is exactly one place where the
// overall block, the status and the provenance are assembled.
func canonicalize(criteria []contract.CriterionResult, meta CanonicalMeta) contract.Evaluation {
	var scored []float64
	var included, excluded []contract.CriterionID
	for _, c := range criteria {
		if c.Scored() && c.Band != nil {
			scored = append(scored, *c.Band)
			included = append(included, c.CriterionID)
			continue
		}
		excluded = append(excluded, c.CriterionID)
	}

	agg := aggregateBands(scored, len(criteria))

	status := contract.StatusComplete
	switch {
	case agg.CompletedCount == 0:
		status = contract.StatusFailed
	case agg.Partial:
		status = contract.StatusPartial
	}

	createdAt := meta.CreatedAt
	if createdAt.IsZero() {
		createdAt = time.Now().UTC()
	}

	return contract.Evaluation{
		SchemaVersion:  contract.SchemaVersion,
		EvaluationID:   meta.EvaluationID,
		Mode:           meta.Mode,
		Status:         status,
		ScoreSemantics: contract.ScoreSemantics,
		Criteria:       criteria,
		Overall: contract.Overall{
			Band:                agg.OverallBand,
			UnroundedMean:       agg.UnroundedMean,
			IncludedCriteria:    included,
			ExcludedCriteria:    excluded,
			RoundingRule:        contract.RoundingRuleV1,
			MinCriteriaRequired: MinCriteriaForOverallBand,
		},
		Provenance: contract.Provenance{
			CreatedAt:        createdAt,
			ScorerVersion:    meta.ScorerVersion,
			RubricID:         contract.RubricID,
			RubricVersion:    contract.RubricVersion,
			RubricSHA256:     contract.RubricSHA256(),
			LLMProvider:      meta.LLMProvider,
			LLMModel:         meta.LLMModel,
			STTProvider:      meta.STTProvider,
			STTModel:         meta.STTModel,
			AudioFormat:      meta.AudioFormat,
			TranscriptSHA256: meta.TranscriptSHA256,
			Measurements:     meta.Measurements,
		},
	}
}

// CanonicalizeSwarm converts a practice result to the canonical evaluation.
func CanonicalizeSwarm(r SwarmResult, meta CanonicalMeta) contract.Evaluation {
	criteria := make([]contract.CriterionResult, 0, len(CriterionOrder))
	// CriterionOrder, not a map range: ranging a map is randomised in Go, and
	// the criteria array's order is semantic -- a UI renders them in it.
	for _, name := range CriterionOrder {
		res, ok := r.Dimensions[name]
		if !ok {
			continue
		}
		id, ok := canonicalCriterionID[name]
		if !ok {
			continue
		}
		status, band, reason := classifyOutcome(res.Band, res.TimedOut, res.Error)
		criteria = append(criteria, contract.CriterionResult{
			CriterionID:       id,
			Status:            status,
			Band:              band,
			UnavailableReason: reason,
			Summary:           res.Feedback,
			// Already resolved against the frozen rubric by parseRubricMatches;
			// an unresolvable citation never reaches this point.
			RubricMatches: res.RubricMatches,
		})
	}
	return canonicalize(criteria, meta)
}

// CanonicalizeHolistic converts an exam result to the canonical evaluation.
//
// The body mirrors CanonicalizeSwarm rather than sharing a generic, because the
// two source structs differ only in which field holds the summary. What must
// not diverge is the classification and the arithmetic, and those are shared.
func CanonicalizeHolistic(r HolisticSwarmResult, meta CanonicalMeta) contract.Evaluation {
	criteria := make([]contract.CriterionResult, 0, len(CriterionOrder))
	for _, name := range CriterionOrder {
		res, ok := r.Dimensions[name]
		if !ok {
			continue
		}
		id, ok := canonicalCriterionID[name]
		if !ok {
			continue
		}
		status, band, reason := classifyOutcome(res.Band, res.TimedOut, res.Error)
		criteria = append(criteria, contract.CriterionResult{
			CriterionID:       id,
			Status:            status,
			Band:              band,
			UnavailableReason: reason,
			Summary:           res.OverallFeedback,
			// Already resolved against the frozen rubric by parseRubricMatches;
			// an unresolvable citation never reaches this point.
			RubricMatches: res.RubricMatches,
		})
	}
	return canonicalize(criteria, meta)
}
