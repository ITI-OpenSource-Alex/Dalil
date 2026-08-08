package contract

import (
	"fmt"
	"sort"
	"strings"
)

// SPEAK-EVAL-008 — what a surface is allowed to display.
//
// Validate() answers "is this evaluation well-formed". That is not the question
// a UI has. A UI has one claim at a time and needs to know whether *this* claim
// may be shown, and if not, what to say instead.
//
// The distinction matters because the failure mode is asymmetric. An
// unexplainable band is merely unhelpful; a band displayed beside a fabricated
// justification is worse than one displayed bare, because the justification is
// what makes it persuasive. A student who is told "band 6, you hesitated at 'the
// small village'" and finds no such phrase in their transcript has been given
// false evidence, and the only thing that made it credible was the specificity.
//
// So the rule here is: a claim whose evidence does not resolve is WITHHELD, and
// the withholding is counted and surfaced rather than silent. The acceptance
// criterion is "invalid explanations are never silently shown" -- both halves,
// and the second half is the one that is easy to skip.
//
// Nothing in this file regenerates or repairs. An explanation is an artifact of
// the run that produced it; rebuilding it later would produce different text for
// the same band, which is how history comes to disagree with what the student
// was originally told.

// ClaimKind distinguishes what a displayed statement rests on.
type ClaimKind string

const (
	// ClaimRubric cites a descriptor from the frozen rubric.
	ClaimRubric ClaimKind = "rubric"
	// ClaimEvidence quotes the transcript, an audio interval or a measurement.
	ClaimEvidence ClaimKind = "evidence"
	// ClaimSummary is the criterion's prose. It rests on the two above and is
	// shown only when at least one of them resolved -- prose with nothing
	// underneath it is the most persuasive kind of unfounded claim.
	ClaimSummary ClaimKind = "summary"
	// ClaimAction is an improvement suggestion.
	ClaimAction ClaimKind = "action"
)

// WithholdReason says why a claim is not renderable. Each value maps to
// different user-facing copy, which is why they are distinct rather than one
// "invalid".
type WithholdReason string

const (
	WithholdUnresolvedDescriptor WithholdReason = "descriptor_not_in_rubric"
	WithholdDescriptorMismatch   WithholdReason = "descriptor_belongs_to_another_criterion"
	WithholdQuoteNotInTranscript WithholdReason = "quote_not_found_at_offsets"
	WithholdMeasurementMissing   WithholdReason = "measurement_not_in_provenance"
	WithholdIncompleteEvidence   WithholdReason = "evidence_incomplete"
	WithholdNoSupport            WithholdReason = "no_resolved_support"
)

// Claim is one displayable statement with everything a surface needs to render
// it and nothing it needs to interpret.
type Claim struct {
	Kind ClaimKind
	Text string

	// DescriptorID and DescriptorBand are set for ClaimRubric. Already resolved
	// against the frozen rubric -- a surface must never look these up itself,
	// because a second lookup is a second chance to disagree.
	DescriptorID   string
	DescriptorBand float64
	Polarity       Polarity

	// Quote, CharStart and CharEnd are set for a transcript-span claim, verified
	// to appear at those offsets.
	Quote     string
	CharStart int
	CharEnd   int

	// AudioStartS and AudioEndS locate the claim in the recording.
	AudioStartS float64
	AudioEndS   float64

	// MeasurementID, MeasurementValue and MeasurementUnit are set for a
	// measurement reference.
	MeasurementID    string
	MeasurementValue float64
	MeasurementUnit  Unit

	// TurnID and Part are forward compatibility for the interviewer work: once
	// a session is a multi-turn interview, "you hesitated here" has to resolve to
	// which question was being answered. Empty until then, and a surface that
	// ignores them today keeps working.
	TurnID string
	Part   int
}

// WithheldClaim is a claim that could not be shown, and why.
//
// Retained rather than dropped so a surface can say "2 further observations
// could not be verified" instead of quietly showing fewer. A student comparing
// two sessions should be able to tell a quiet session from a broken one.
type WithheldClaim struct {
	Kind   ClaimKind
	Reason WithholdReason
	Detail string
}

// RenderableCriterion is what a surface may display for one criterion.
type RenderableCriterion struct {
	CriterionID CriterionID
	Status      CriterionStatus

	// Band is nil for an unavailable criterion. Never 0.0 -- see the contract's
	// note on why those are different values.
	Band              *float64
	UnavailableReason UnavailableReason

	Claims   []Claim
	Withheld []WithheldClaim

	// Limitations are explicit statements of what this criterion did NOT assess.
	// Required, not decorative: Pronunciation reasons from recognition
	// confidence and pause structure, which says nothing about individual
	// sounds, and a student who reads "Pronunciation 6.0" without that caveat
	// has been told something the system did not measure.
	Limitations []string
}

// Renderable is a whole evaluation, reduced to what may be shown.
type Renderable struct {
	EvaluationID string
	Mode         Mode
	Status       Status

	Band          *float64
	UnroundedMean *float64
	// BandWithheldReason explains an absent overall band in words a surface can
	// display. Empty when a band is present.
	BandWithheldReason string

	Criteria []RenderableCriterion

	// ScoreSemantics is carried through so a surface cannot render a band
	// without the qualifier attached to it.
	ScoreSemantics string
	RubricID       string
	RubricVersion  string
}

// AnyWithheld reports whether anything was suppressed anywhere.
func (r Renderable) AnyWithheld() bool {
	for _, c := range r.Criteria {
		if len(c.Withheld) > 0 {
			return true
		}
	}
	return false
}

// WithheldCount is what a surface displays as "n observations could not be
// verified".
func (r Renderable) WithheldCount() int {
	total := 0
	for _, c := range r.Criteria {
		total += len(c.Withheld)
	}
	return total
}

// BuildRenderable reduces an evaluation to displayable claims.
//
// `transcript` is the text the offsets refer to. An empty transcript does not
// silently pass transcript-span claims: they are withheld, because a quote that
// cannot be checked is exactly the kind that should not be shown.
//
// This never errors. A surface always gets something renderable, even if that
// something is a criterion with a band, no claims and an explicit count of what
// was suppressed. Returning an error would push the decision back to the caller,
// and the caller is a React component.
func BuildRenderable(e Evaluation, transcript string) Renderable {
	out := Renderable{
		EvaluationID:   e.EvaluationID,
		Mode:           e.Mode,
		Status:         e.Status,
		Band:           e.Overall.Band,
		UnroundedMean:  e.Overall.UnroundedMean,
		ScoreSemantics: e.ScoreSemantics,
		RubricID:       e.Provenance.RubricID,
		RubricVersion:  e.Provenance.RubricVersion,
	}

	if e.Overall.Band == nil {
		scored := 0
		for _, c := range e.Criteria {
			if c.Scored() {
				scored++
			}
		}
		out.BandWithheldReason = fmt.Sprintf(
			"An overall band needs at least %d of the %d criteria. %d completed, so no "+
				"overall band was calculated. The criteria that did complete are shown below.",
			e.Overall.MinCriteriaRequired, len(e.Criteria), scored,
		)
	}

	measurements := make(map[string]Measurement, len(e.Provenance.Measurements))
	for _, m := range e.Provenance.Measurements {
		measurements[m.ID] = m
	}

	for _, criterion := range e.Criteria {
		out.Criteria = append(out.Criteria, buildCriterion(criterion, transcript, measurements))
	}

	return out
}

func buildCriterion(
	c CriterionResult,
	transcript string,
	measurements map[string]Measurement,
) RenderableCriterion {
	rc := RenderableCriterion{
		CriterionID:       c.CriterionID,
		Status:            c.Status,
		Band:              c.Band,
		UnavailableReason: c.UnavailableReason,
		Limitations:       append([]string(nil), c.Limitations...),
	}

	// An unavailable criterion has nothing to justify. Showing rubric citations
	// beside "could not be assessed" would imply an assessment happened.
	if !c.Scored() {
		return rc
	}

	for _, match := range c.RubricMatches {
		descriptor, ok := LookupDescriptor(match.DescriptorID)
		if !ok {
			rc.Withheld = append(rc.Withheld, WithheldClaim{
				Kind:   ClaimRubric,
				Reason: WithholdUnresolvedDescriptor,
				Detail: fmt.Sprintf("descriptor %q is not in the frozen rubric", match.DescriptorID),
			})
			continue
		}
		// A real descriptor cited under the wrong criterion is the citation most
		// likely to survive a careless check, because the id resolves.
		if descriptor.Criterion != c.CriterionID {
			rc.Withheld = append(rc.Withheld, WithheldClaim{
				Kind:   ClaimRubric,
				Reason: WithholdDescriptorMismatch,
				Detail: fmt.Sprintf("descriptor %q belongs to %s", match.DescriptorID, descriptor.Criterion),
			})
			continue
		}
		rc.Claims = append(rc.Claims, Claim{
			Kind:           ClaimRubric,
			Text:           descriptor.Text,
			DescriptorID:   descriptor.ID,
			DescriptorBand: descriptor.Band,
			Polarity:       match.Polarity,
		})
	}

	for _, ev := range c.Evidence {
		claim, withheld := buildEvidenceClaim(ev, transcript, measurements)
		if withheld != nil {
			rc.Withheld = append(rc.Withheld, *withheld)
			continue
		}
		rc.Claims = append(rc.Claims, *claim)
	}

	// The summary rests on everything above it. Prose with nothing underneath is
	// the most persuasive kind of unfounded claim -- it reads as an assessment
	// while resting on nothing a reader can check.
	if c.Summary != "" {
		if len(rc.Claims) > 0 {
			rc.Claims = append(rc.Claims, Claim{Kind: ClaimSummary, Text: c.Summary})
		} else {
			rc.Withheld = append(rc.Withheld, WithheldClaim{
				Kind:   ClaimSummary,
				Reason: WithholdNoSupport,
				Detail: "no rubric citation or evidence resolved, so the summary has nothing to rest on",
			})
		}
	}

	for _, action := range c.ImprovementActions {
		if action.Action == "" {
			continue
		}
		text := action.Action
		if action.Because != "" {
			text = action.Action + " (" + action.Because + ")"
		}
		rc.Claims = append(rc.Claims, Claim{Kind: ClaimAction, Text: text})
	}

	// Pronunciation's limitation is not optional. GOA-133 established that this
	// criterion reasons from recognition confidence and pause structure, which
	// supports intelligibility and phrasing and says nothing about individual
	// sounds, word stress or intonation. A band shown without that is a claim the
	// system never measured.
	if c.CriterionID == CriterionPronunciation && !hasPronunciationLimitation(rc.Limitations) {
		rc.Limitations = append(rc.Limitations,
			"This score reflects how clearly your speech was recognised and how it was "+
				"paced. It does not assess individual sounds, word stress or intonation.")
	}

	return rc
}

func buildEvidenceClaim(
	ev Evidence,
	transcript string,
	measurements map[string]Measurement,
) (*Claim, *WithheldClaim) {
	switch ev.Kind {
	case EvidenceTranscriptSpan:
		if ev.Quote == "" || ev.CharStart == nil || ev.CharEnd == nil {
			return nil, &WithheldClaim{
				Kind: ClaimEvidence, Reason: WithholdIncompleteEvidence,
				Detail: "a transcript span needs a quote and both offsets",
			}
		}
		// Verified against the transcript, not trusted. An offset pair that does
		// not contain the quote points a student at words they did not say.
		start, end := *ev.CharStart, *ev.CharEnd
		if start < 0 || end > len(transcript) || start >= end ||
			transcript[start:end] != ev.Quote {
			return nil, &WithheldClaim{
				Kind: ClaimEvidence, Reason: WithholdQuoteNotInTranscript,
				Detail: fmt.Sprintf("%q does not appear at [%d, %d]", ev.Quote, start, end),
			}
		}
		return &Claim{
			Kind: ClaimEvidence, Text: ev.SupportsClaim,
			Quote: ev.Quote, CharStart: start, CharEnd: end,
			Part: partOf(ev),
		}, nil

	case EvidenceMeasurementRef:
		m, ok := measurements[ev.MeasurementID]
		if !ok {
			return nil, &WithheldClaim{
				Kind: ClaimEvidence, Reason: WithholdMeasurementMissing,
				Detail: fmt.Sprintf("measurement %q is not in provenance", ev.MeasurementID),
			}
		}
		return &Claim{
			Kind: ClaimEvidence, Text: ev.SupportsClaim,
			MeasurementID: m.ID, MeasurementValue: m.Value, MeasurementUnit: m.Unit,
			Part: partOf(ev),
		}, nil

	case EvidenceAudioInterval:
		if ev.AudioStartS == nil || ev.AudioEndS == nil || *ev.AudioEndS <= *ev.AudioStartS {
			return nil, &WithheldClaim{
				Kind: ClaimEvidence, Reason: WithholdIncompleteEvidence,
				Detail: "an audio interval needs a start before its end",
			}
		}
		return &Claim{
			Kind: ClaimEvidence, Text: ev.SupportsClaim,
			AudioStartS: *ev.AudioStartS, AudioEndS: *ev.AudioEndS,
			Part: partOf(ev),
		}, nil

	default:
		// part_or_turn and absence_or_distribution carry no locator to verify, so
		// they are shown on their claim text alone.
		if strings.TrimSpace(ev.SupportsClaim) == "" {
			return nil, &WithheldClaim{
				Kind: ClaimEvidence, Reason: WithholdIncompleteEvidence,
				Detail: "evidence with no claim attached",
			}
		}
		return &Claim{Kind: ClaimEvidence, Text: ev.SupportsClaim, Part: partOf(ev)}, nil
	}
}

func partOf(ev Evidence) int {
	if ev.Part == nil {
		return 0
	}
	return *ev.Part
}

func hasPronunciationLimitation(limitations []string) bool {
	for _, l := range limitations {
		lowered := strings.ToLower(l)
		if strings.Contains(lowered, "individual sound") || strings.Contains(lowered, "intonation") {
			return true
		}
	}
	return false
}

// DescriptorsCited returns the descriptor ids a renderable actually shows, in
// order. Used by the persistence layer to record what a student was told.
func (r Renderable) DescriptorsCited() []string {
	seen := map[string]bool{}
	var ids []string
	for _, c := range r.Criteria {
		for _, claim := range c.Claims {
			if claim.Kind == ClaimRubric && !seen[claim.DescriptorID] {
				seen[claim.DescriptorID] = true
				ids = append(ids, claim.DescriptorID)
			}
		}
	}
	sort.Strings(ids)
	return ids
}
