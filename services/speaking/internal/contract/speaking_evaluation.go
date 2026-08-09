// Package contract holds the Go representation of the canonical speaking
// evaluation, packages/contracts/schemas/speaking-evaluation-v1.schema.json.
//
// SPEAK-EVAL-003.
//
// WHY THE TYPES LIVE HERE AND NOT IN packages/contracts/go
//
// The plan left the Go location to an architecture decision. The speaking
// service is the only Go consumer of this contract, and a shared Go package
// would need its own module plus a `replace` directive in every service that
// imports it -- real build complexity bought for a single consumer. The types
// live here instead, and speaking_evaluation_test.go validates them against the
// JSON Schema so "the Go struct matches the contract" is a test rather than a
// convention. If a second Go service ever needs this, promote the package then.
//
// TWO RULES RUN THROUGH EVERY TYPE
//
//  1. Status is separate from value. A criterion that did not complete has
//     Status "unavailable" and a nil Band. Band 0.0 is a real IELTS value; it
//     must never stand in for "not measured". This codebase has shipped that
//     defect at least four times (BUG-055, BUG-040, the holistic path in
//     GOA-134, the exam histogram in the dev merge), which is why it is encoded
//     in the types and not left to reviewers.
//
//  2. Every claim is addressable. A rubric match names a descriptor id from the
//     frozen rubric; evidence names a transcript offset, an audio interval or a
//     measurement id. Validate() resolves them all, so a displayed reason is
//     checkable rather than merely fluent.
package contract

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

// SchemaVersion is carried by every result. A breaking field or meaning change
// creates v2; additive optional fields may stay v1 only if older consumers
// ignore unknown keys safely.
const SchemaVersion = "speaking-evaluation/v1"

// ScoreSemantics is deliberately fixed and deliberately not "ielts_band". This
// system is not a certified examiner, and the payload must not be able to say
// it is.
const ScoreSemantics = "estimated_ielts_practice_band"

// CriterionID identifies one of the four official IELTS speaking criteria.
//
// Snake_case ids rather than the display strings ("Fluency and Coherence") the
// swarm keys its map by: a display string is a label, and labels change.
// GOA-133 renamed pronunciation in the UI without touching the underlying
// criterion, which is exactly the separation these ids buy.
type CriterionID string

const (
	CriterionFluencyCoherence CriterionID = "fluency_coherence"
	CriterionLexicalResource  CriterionID = "lexical_resource"
	CriterionGrammaticalRange CriterionID = "grammatical_range"
	CriterionPronunciation    CriterionID = "pronunciation"
)

// CriterionOrder fixes presentation order. Ranging a map is randomised in Go,
// so without this the summary reorders itself on every request.
var CriterionOrder = [...]CriterionID{
	CriterionFluencyCoherence,
	CriterionLexicalResource,
	CriterionGrammaticalRange,
	CriterionPronunciation,
}

// Mode records which transport produced a result. The scoring core is identical
// across all three; only the envelope differs. "benchmark" exists so an eval run
// can never be mistaken for a user's result.
type Mode string

const (
	ModePractice  Mode = "practice"
	ModeExam      Mode = "exam"
	ModeBenchmark Mode = "benchmark"
)

type Status string

const (
	StatusComplete Status = "complete"
	StatusPartial  Status = "partial"
	StatusFailed   Status = "failed"
)

type CriterionStatus string

const (
	CriterionScored      CriterionStatus = "scored"
	CriterionUnavailable CriterionStatus = "unavailable"
)

// UnavailableReason distinguishes the ways a criterion can fail to produce a
// score. They are not interchangeable: a deadline may succeed on retry, a
// provider error will not, and insufficient_evidence never will for this input.
type UnavailableReason string

const (
	ReasonProviderError        UnavailableReason = "provider_error"
	ReasonDeadlineExceeded     UnavailableReason = "deadline_exceeded"
	ReasonInvalidOutput        UnavailableReason = "invalid_output"
	ReasonInsufficientEvidence UnavailableReason = "insufficient_evidence"
)

// Polarity says what a cited descriptor establishes.
//
// PolarityCapsBelow is the one that makes an explanation answer "why not a 7"
// rather than only "why a 6", which is the difference between a justification a
// student can act on and one they can only accept.
type Polarity string

const (
	PolaritySupports      Polarity = "supports"
	PolarityCapsBelow     Polarity = "caps_below"
	PolarityReachesToward Polarity = "reaches_toward"
)

type EvidenceKind string

const (
	EvidenceTranscriptSpan EvidenceKind = "transcript_span"
	EvidenceAudioInterval  EvidenceKind = "audio_interval"
	EvidenceMeasurementRef EvidenceKind = "measurement_ref"
	EvidencePartOrTurn     EvidenceKind = "part_or_turn"
	EvidenceDistribution   EvidenceKind = "absence_or_distribution"
)

type Unit string

const (
	UnitWordsPerMinute Unit = "words_per_minute"
	UnitSeconds        Unit = "seconds"
	UnitCount          Unit = "count"
	UnitRatio          Unit = "ratio"
	UnitProbability    Unit = "probability"
)

// RoundingRuleV1 is the versioned id of the IELTS half-band rounding applied.
// Named rather than assumed, so a change to it is visible in stored results
// instead of silently reinterpreting every historical score.
const RoundingRuleV1 = "ielts_half_band_v1"

// Evaluation is the canonical result. Practice and exam both produce this; the
// WebSocket frame and the holistic REST body are adapters over it.
type Evaluation struct {
	SchemaVersion  string            `json:"schema_version"`
	EvaluationID   string            `json:"evaluation_id"`
	Mode           Mode              `json:"mode"`
	Status         Status            `json:"status"`
	ScoreSemantics string            `json:"score_semantics"`
	Criteria       []CriterionResult `json:"criteria"`
	Overall        Overall           `json:"overall"`
	Provenance     Provenance        `json:"provenance"`
	Telemetry      *Telemetry        `json:"telemetry,omitempty"`
}

// CriterionResult is one criterion's outcome.
type CriterionResult struct {
	CriterionID CriterionID     `json:"criterion_id"`
	Status      CriterionStatus `json:"status"`
	// Band is a pointer and omitempty: present if and only if Status is
	// "scored". A plain float64 makes "not measured" and "scored zero" the same
	// value, which is the defect this contract exists to make unrepresentable.
	Band *float64 `json:"band,omitempty"`
	// UnavailableReason is present if and only if Status is "unavailable".
	UnavailableReason UnavailableReason `json:"unavailable_reason,omitempty"`

	Summary            string              `json:"summary,omitempty"`
	RubricMatches      []RubricMatch       `json:"rubric_matches,omitempty"`
	Evidence           []Evidence          `json:"evidence,omitempty"`
	Measurements       []string            `json:"measurements,omitempty"`
	Limitations        []string            `json:"limitations,omitempty"`
	ImprovementActions []ImprovementAction `json:"improvement_actions,omitempty"`
}

// Scored reports whether this criterion contributed a band.
func (c CriterionResult) Scored() bool {
	return c.Status == CriterionScored && c.Band != nil
}

type RubricMatch struct {
	RubricID       string   `json:"rubric_id"`
	RubricVersion  string   `json:"rubric_version"`
	DescriptorID   string   `json:"descriptor_id"`
	DescriptorBand float64  `json:"descriptor_band"`
	Polarity       Polarity `json:"polarity"`
	Application    string   `json:"application,omitempty"`
}

type Evidence struct {
	Kind          EvidenceKind `json:"kind"`
	SupportsClaim string       `json:"supports_claim"`

	Quote     string `json:"quote,omitempty"`
	CharStart *int   `json:"char_start,omitempty"`
	CharEnd   *int   `json:"char_end,omitempty"`

	AudioStartS *float64 `json:"audio_start_s,omitempty"`
	AudioEndS   *float64 `json:"audio_end_s,omitempty"`

	MeasurementID string `json:"measurement_id,omitempty"`
	TurnID        string `json:"turn_id,omitempty"`
	Part          *int   `json:"part,omitempty"`
}

type ImprovementAction struct {
	Action  string `json:"action"`
	Because string `json:"because,omitempty"`
}

// Overall carries the aggregate and the arithmetic behind it.
type Overall struct {
	// Band is absent -- not null, not zero -- when fewer than
	// MinCriteriaRequired criteria scored. A band averaged from one surviving
	// agent describes which agents survived, not the candidate (BUG-040).
	Band *float64 `json:"band,omitempty"`
	// UnroundedMean is shown so a student can see the arithmetic rather than be
	// asked to trust it, and so a mean that disagrees with the band is
	// detectable rather than invisible.
	UnroundedMean       *float64      `json:"unrounded_mean,omitempty"`
	IncludedCriteria    []CriterionID `json:"included_criteria"`
	ExcludedCriteria    []CriterionID `json:"excluded_criteria,omitempty"`
	RoundingRule        string        `json:"rounding_rule"`
	MinCriteriaRequired int           `json:"min_criteria_required"`
}

type Measurement struct {
	ID               string  `json:"id"`
	Name             string  `json:"name"`
	Value            float64 `json:"value"`
	Unit             Unit    `json:"unit"`
	ExtractorVersion string  `json:"extractor_version"`
	Scope            string  `json:"scope,omitempty"`
}

// Provenance is what produced this score: enough to reproduce it, or at least
// to explain why it cannot be reproduced.
type Provenance struct {
	CreatedAt     time.Time `json:"created_at"`
	ScorerVersion string    `json:"scorer_version"`
	RubricID      string    `json:"rubric_id"`
	RubricVersion string    `json:"rubric_version"`
	RubricSHA256  string    `json:"rubric_sha256,omitempty"`

	LLMProvider string `json:"llm_provider,omitempty"`
	// LLMModel is the EFFECTIVE model, read from configuration at call time.
	// The Langfuse span used to hardcode a Haiku id while the service ran Opus,
	// which made every model-to-model comparison in telemetry meaningless.
	LLMModel          string   `json:"llm_model,omitempty"`
	PromptTemplateIDs []string `json:"prompt_template_ids,omitempty"`

	STTProvider      string `json:"stt_provider,omitempty"`
	STTModel         string `json:"stt_model,omitempty"`
	TranscriptSHA256 string `json:"transcript_sha256,omitempty"`
	// AudioFormat is the declared container. Recorded because SPEAK-EVAL-002
	// established that a mislabelled format silently produces a score from noise.
	AudioFormat             string `json:"audio_format,omitempty"`
	FeatureExtractorVersion string `json:"feature_extractor_version,omitempty"`

	Measurements []Measurement `json:"measurements,omitempty"`
}

type Telemetry struct {
	TotalLatencyMs   int64   `json:"total_latency_ms,omitempty"`
	TranscriptionMs  int64   `json:"transcription_ms,omitempty"`
	AudioDurationS   float64 `json:"audio_duration_s,omitempty"`
	PromptTokens     int     `json:"prompt_tokens,omitempty"`
	CompletionTokens int     `json:"completion_tokens,omitempty"`
	// CostUSD is a pointer so an unpriced model records null rather than 0.0
	// (GOA-135). "We could not price this" and "this was free" are different
	// facts and must not share a representation.
	CostUSD *float64 `json:"cost_usd"`
}

// --- validation -----------------------------------------------------------

var (
	ErrSchemaVersion = errors.New("unsupported schema version")
	ErrStatusValue   = errors.New("status and value disagree")
	ErrBandStep      = errors.New("band is not a half-band step")
	ErrUnknownRef    = errors.New("reference does not resolve")
	ErrEvidenceShape = errors.New("evidence is missing a field its kind requires")
	ErrCalculation   = errors.New("overall does not agree with its criteria")
)

// ValidationError names the exact place a result failed, so a failure is
// actionable rather than merely a rejection.
type ValidationError struct {
	Path string
	Err  error
	Msg  string
}

func (e ValidationError) Error() string {
	return fmt.Sprintf("%s: %s (%v)", e.Path, e.Msg, e.Err)
}

func (e ValidationError) Unwrap() error { return e.Err }

// Validate checks everything the JSON Schema cannot: that references resolve,
// that quotes appear where they claim to, and that the overall band agrees with
// the criteria it says it came from.
//
// transcript may be empty, in which case transcript-span offsets are not
// checked; every other rule still applies. allowedDescriptors is the frozen
// rubric's id set -- an empty map disables that check, which is only correct for
// a caller that has no rubric loaded.
//
// Returns every problem rather than the first, because a result with three
// broken references should not need three round trips to diagnose.
func (e Evaluation) Validate(transcript string, allowedDescriptors map[string]float64) []ValidationError {
	var problems []ValidationError

	if e.SchemaVersion != SchemaVersion {
		problems = append(problems, ValidationError{
			Path: "schema_version", Err: ErrSchemaVersion,
			Msg: fmt.Sprintf("got %q, want %q", e.SchemaVersion, SchemaVersion),
		})
	}
	if e.ScoreSemantics != ScoreSemantics {
		problems = append(problems, ValidationError{
			Path: "score_semantics", Err: ErrStatusValue,
			Msg: fmt.Sprintf("got %q, want %q -- this system must not claim to be a certified examiner", e.ScoreSemantics, ScoreSemantics),
		})
	}

	measurementIDs := map[string]bool{}
	for _, m := range e.Provenance.Measurements {
		measurementIDs[m.ID] = true
	}

	var scored []float64
	for i, c := range e.Criteria {
		path := fmt.Sprintf("criteria[%d](%s)", i, c.CriterionID)
		problems = append(problems, c.validate(path, transcript, allowedDescriptors, measurementIDs)...)
		if c.Scored() {
			scored = append(scored, *c.Band)
		}
	}

	problems = append(problems, e.validateOverall(scored)...)
	return problems
}

func (c CriterionResult) validate(
	path, transcript string,
	allowedDescriptors map[string]float64,
	measurementIDs map[string]bool,
) []ValidationError {
	var problems []ValidationError

	switch c.Status {
	case CriterionScored:
		if c.Band == nil {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrStatusValue,
				Msg: "status is scored but no band is present",
			})
		} else if !IsHalfBand(*c.Band) {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrBandStep,
				Msg: fmt.Sprintf("band %v is not a half-band step; no examiner could award it", *c.Band),
			})
		}
		if c.UnavailableReason != "" {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrStatusValue,
				Msg: "a scored criterion carries an unavailable_reason",
			})
		}
	case CriterionUnavailable:
		if c.Band != nil {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrStatusValue,
				Msg: fmt.Sprintf(
					"an unavailable criterion carries band %v. Band 0.0 is a real IELTS "+
						"value meaning the candidate said nothing usable; it must never "+
						"stand in for 'not measured' (BUG-055)", *c.Band),
			})
		}
		if c.UnavailableReason == "" {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrStatusValue,
				Msg: "an unavailable criterion gives no reason",
			})
		}
	default:
		problems = append(problems, ValidationError{
			Path: path, Err: ErrStatusValue,
			Msg: fmt.Sprintf("unknown status %q", c.Status),
		})
	}

	for j, m := range c.RubricMatches {
		mp := fmt.Sprintf("%s.rubric_matches[%d]", path, j)
		if len(allowedDescriptors) == 0 {
			continue
		}
		band, ok := allowedDescriptors[m.DescriptorID]
		if !ok {
			problems = append(problems, ValidationError{
				Path: mp, Err: ErrUnknownRef,
				Msg: fmt.Sprintf(
					"descriptor %q is not in the frozen rubric. A model may cite only "+
						"ids supplied in its request; anything else is invented",
					m.DescriptorID),
			})
			continue
		}
		if band != m.DescriptorBand {
			problems = append(problems, ValidationError{
				Path: mp, Err: ErrUnknownRef,
				Msg: fmt.Sprintf("descriptor %q is band %v in the rubric, cited as %v",
					m.DescriptorID, band, m.DescriptorBand),
			})
		}
	}

	for j, ev := range c.Evidence {
		problems = append(problems, ev.validate(
			fmt.Sprintf("%s.evidence[%d]", path, j), transcript, measurementIDs)...)
	}

	for _, id := range c.Measurements {
		if !measurementIDs[id] {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrUnknownRef,
				Msg: fmt.Sprintf("measurement %q is not in provenance.measurements", id),
			})
		}
	}

	return problems
}

func (ev Evidence) validate(path, transcript string, measurementIDs map[string]bool) []ValidationError {
	var problems []ValidationError

	if ev.SupportsClaim == "" {
		problems = append(problems, ValidationError{
			Path: path, Err: ErrEvidenceShape,
			Msg: "evidence states no claim; evidence attached to nothing is decoration",
		})
	}

	switch ev.Kind {
	case EvidenceTranscriptSpan:
		if ev.CharStart == nil || ev.CharEnd == nil || ev.Quote == "" {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrEvidenceShape,
				Msg: "a transcript span needs a quote and both offsets, or it cannot be checked",
			})
			break
		}
		if *ev.CharEnd < *ev.CharStart {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrEvidenceShape,
				Msg: fmt.Sprintf("offsets are inverted (%d..%d)", *ev.CharStart, *ev.CharEnd),
			})
			break
		}
		if transcript == "" {
			break // nothing to check against; caller supplied no transcript
		}
		if *ev.CharEnd > len(transcript) {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrUnknownRef,
				Msg: fmt.Sprintf("offsets %d..%d run past the transcript (%d chars)",
					*ev.CharStart, *ev.CharEnd, len(transcript)),
			})
			break
		}
		// The quote must actually be there. This is what stops a paraphrase
		// being presented as a quotation -- the single most persuasive thing an
		// explanation can get wrong, because it looks like proof.
		if got := transcript[*ev.CharStart:*ev.CharEnd]; !strings.EqualFold(strings.TrimSpace(got), strings.TrimSpace(ev.Quote)) {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrUnknownRef,
				Msg: fmt.Sprintf("quote %q does not appear at %d..%d; the transcript has %q",
					ev.Quote, *ev.CharStart, *ev.CharEnd, got),
			})
		}
	case EvidenceAudioInterval:
		if ev.AudioStartS == nil || ev.AudioEndS == nil {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrEvidenceShape,
				Msg: "an audio interval needs both bounds",
			})
		} else if *ev.AudioEndS < *ev.AudioStartS {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrEvidenceShape,
				Msg: "audio interval is inverted",
			})
		}
	case EvidenceMeasurementRef:
		if ev.MeasurementID == "" {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrEvidenceShape, Msg: "measurement reference names no id",
			})
		} else if len(measurementIDs) > 0 && !measurementIDs[ev.MeasurementID] {
			problems = append(problems, ValidationError{
				Path: path, Err: ErrUnknownRef,
				Msg: fmt.Sprintf("measurement %q is not in provenance.measurements", ev.MeasurementID),
			})
		}
	case EvidencePartOrTurn, EvidenceDistribution:
		// No structural requirement beyond a stated claim.
	default:
		problems = append(problems, ValidationError{
			Path: path, Err: ErrEvidenceShape,
			Msg: fmt.Sprintf("unknown evidence kind %q", ev.Kind),
		})
	}

	return problems
}

func (e Evaluation) validateOverall(scored []float64) []ValidationError {
	var problems []ValidationError
	o := e.Overall

	if len(o.IncludedCriteria) != len(scored) {
		problems = append(problems, ValidationError{
			Path: "overall.included_criteria", Err: ErrCalculation,
			Msg: fmt.Sprintf("lists %d criteria but %d actually scored",
				len(o.IncludedCriteria), len(scored)),
		})
	}

	enough := len(scored) >= o.MinCriteriaRequired

	switch {
	case o.Band == nil && enough:
		problems = append(problems, ValidationError{
			Path: "overall.band", Err: ErrCalculation,
			Msg: fmt.Sprintf("%d criteria scored (threshold %d) but no overall band was computed",
				len(scored), o.MinCriteriaRequired),
		})
	case o.Band != nil && !enough:
		problems = append(problems, ValidationError{
			Path: "overall.band", Err: ErrCalculation,
			Msg: fmt.Sprintf(
				"an overall band of %v was computed from %d criteria, below the "+
					"threshold of %d. Such a band describes which agents survived, "+
					"not the candidate (BUG-040)",
				*o.Band, len(scored), o.MinCriteriaRequired),
		})
	case o.Band != nil && enough:
		if !IsHalfBand(*o.Band) {
			problems = append(problems, ValidationError{
				Path: "overall.band", Err: ErrBandStep,
				Msg: fmt.Sprintf("overall band %v is not a half-band step", *o.Band),
			})
		}
		// The arithmetic must be reproducible from the parts. A band that does
		// not follow from its own criteria is the calculation-trace equivalent
		// of an unverifiable quote.
		var sum float64
		for _, b := range scored {
			sum += b
		}
		mean := sum / float64(len(scored))
		if want := RoundIELTSBand(mean); want != *o.Band {
			problems = append(problems, ValidationError{
				Path: "overall.band", Err: ErrCalculation,
				Msg: fmt.Sprintf("band %v does not follow from the criteria; mean %.4f rounds to %v",
					*o.Band, mean, want),
			})
		}
		if o.UnroundedMean != nil && !floatsClose(*o.UnroundedMean, mean) {
			problems = append(problems, ValidationError{
				Path: "overall.unrounded_mean", Err: ErrCalculation,
				Msg: fmt.Sprintf("stated mean %v, computed %.4f", *o.UnroundedMean, mean),
			})
		}
	}

	if o.RoundingRule == "" {
		problems = append(problems, ValidationError{
			Path: "overall.rounding_rule", Err: ErrCalculation,
			Msg: "no rounding rule recorded, so the arithmetic cannot be reproduced later",
		})
	}

	return problems
}

// IsHalfBand reports whether b is a legal IELTS band value.
func IsHalfBand(b float64) bool {
	if b < 0 || b > 9 {
		return false
	}
	doubled := b * 2
	return floatsClose(doubled, float64(int(doubled+0.5)))
}

func floatsClose(a, b float64) bool {
	d := a - b
	return d < 1e-9 && d > -1e-9
}

// RoundIELTSBand implements the official half-up rounding rule.
//
// Duplicated deliberately from agents.RoundIELTSBand rather than imported:
// agents imports nothing from contract and contract imports nothing from
// agents, which keeps the dependency one-directional. A test asserts the two
// agree on every value in range, so the duplication cannot drift.
func RoundIELTSBand(average float64) float64 {
	intPart := float64(int(average))
	decPart := average - intPart
	switch {
	case decPart < 0.25:
		return intPart
	case decPart < 0.75:
		return intPart + 0.5
	default:
		return intPart + 1.0
	}
}
