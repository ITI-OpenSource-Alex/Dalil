package contract

import (
	"strings"
	"testing"
)

// SPEAK-EVAL-008 acceptance, in tests:
//
//   - every displayed claim resolves to valid evidence or approved rubric context;
//   - invalid explanations are never silently shown;
//   - partial results and pronunciation limitations are explicit.
//
// The second criterion has two halves and the second half is the one that is
// easy to skip: a suppressed claim must be COUNTED, not merely dropped. A
// student comparing two sessions should be able to tell a quiet session from a
// broken one.

const testTranscript = "I grew up in a small village near the coast and I still go back every summer."

func ptrF(v float64) *float64 { return &v }
func ptrI(v int) *int         { return &v }

func scoredCriterion(id CriterionID, band float64) CriterionResult {
	return CriterionResult{CriterionID: id, Status: CriterionScored, Band: ptrF(band)}
}

func evaluationWith(criteria ...CriterionResult) Evaluation {
	return Evaluation{
		SchemaVersion:  SchemaVersion,
		EvaluationID:   "eval-test",
		Mode:           ModePractice,
		Status:         StatusComplete,
		ScoreSemantics: ScoreSemantics,
		Criteria:       criteria,
		Overall: Overall{
			Band:                ptrF(6.5),
			RoundingRule:        RoundingRuleV1,
			MinCriteriaRequired: 3,
		},
		Provenance: Provenance{RubricID: RubricID, RubricVersion: RubricVersion},
	}
}

func claimsOfKind(rc RenderableCriterion, kind ClaimKind) []Claim {
	var out []Claim
	for _, c := range rc.Claims {
		if c.Kind == kind {
			out = append(out, c)
		}
	}
	return out
}

// --- rubric citations -------------------------------------------------------

func TestARealDescriptorIsRenderedWithItsRubricText(t *testing.T) {
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.RubricMatches = []RubricMatch{{DescriptorID: "fc.6", Polarity: PolaritySupports}}

	r := BuildRenderable(evaluationWith(c), testTranscript)
	claims := claimsOfKind(r.Criteria[0], ClaimRubric)

	if len(claims) != 1 {
		t.Fatalf("got %d rubric claims, want 1", len(claims))
	}
	if claims[0].DescriptorID != "fc.6" || claims[0].DescriptorBand != 6 {
		t.Errorf("descriptor resolved wrongly: %+v", claims[0])
	}
	// The text comes from the frozen rubric, not from the model. A surface that
	// looked it up itself would be a second chance to disagree.
	if !strings.Contains(claims[0].Text, "willing to speak at length") {
		t.Errorf("rubric text not attached: %q", claims[0].Text)
	}
}

func TestAnInventedDescriptorIsWithheldNotShown(t *testing.T) {
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.RubricMatches = []RubricMatch{{DescriptorID: "fc.42", Polarity: PolaritySupports}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(claimsOfKind(rc, ClaimRubric)) != 0 {
		t.Error("an invented descriptor was rendered")
	}
	if len(rc.Withheld) != 1 || rc.Withheld[0].Reason != WithholdUnresolvedDescriptor {
		t.Errorf("not withheld with the right reason: %+v", rc.Withheld)
	}
}

func TestARealDescriptorUnderTheWrongCriterionIsWithheld(t *testing.T) {
	// The citation most likely to survive a careless check, because the id
	// resolves -- it is simply not this criterion's descriptor.
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.RubricMatches = []RubricMatch{{DescriptorID: "lr.7", Polarity: PolaritySupports}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(claimsOfKind(rc, ClaimRubric)) != 0 {
		t.Error("a foreign descriptor was rendered")
	}
	if rc.Withheld[0].Reason != WithholdDescriptorMismatch {
		t.Errorf("reason = %q", rc.Withheld[0].Reason)
	}
}

// --- transcript evidence ----------------------------------------------------

func TestAQuoteIsVerifiedAgainstTheTranscript(t *testing.T) {
	start := strings.Index(testTranscript, "a small village")
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.Evidence = []Evidence{{
		Kind: EvidenceTranscriptSpan, SupportsClaim: "hesitation before a content word",
		Quote: "a small village", CharStart: ptrI(start), CharEnd: ptrI(start + len("a small village")),
	}}

	claims := claimsOfKind(BuildRenderable(evaluationWith(c), testTranscript).Criteria[0], ClaimEvidence)

	if len(claims) != 1 || claims[0].Quote != "a small village" {
		t.Fatalf("verified quote not rendered: %+v", claims)
	}
}

func TestAQuoteThatIsNotAtItsOffsetsIsWithheld(t *testing.T) {
	// The defect this whole file exists to prevent. A student told "you
	// hesitated at 'the bustling metropolis'" who never said it has been given
	// false evidence, and the specificity is what made it credible.
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.Evidence = []Evidence{{
		Kind: EvidenceTranscriptSpan, SupportsClaim: "hesitation",
		Quote: "the bustling metropolis", CharStart: ptrI(0), CharEnd: ptrI(22),
	}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(claimsOfKind(rc, ClaimEvidence)) != 0 {
		t.Error("an unverifiable quote was rendered")
	}
	if rc.Withheld[0].Reason != WithholdQuoteNotInTranscript {
		t.Errorf("reason = %q", rc.Withheld[0].Reason)
	}
}

func TestOffsetsOutsideTheTranscriptAreWithheldNotPanicking(t *testing.T) {
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.Evidence = []Evidence{{
		Kind: EvidenceTranscriptSpan, SupportsClaim: "x",
		Quote: "anything", CharStart: ptrI(5000), CharEnd: ptrI(6000),
	}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(rc.Withheld) != 1 {
		t.Fatalf("out-of-range offsets not withheld: %+v", rc)
	}
}

func TestAnEmptyTranscriptWithholdsRatherThanPasses(t *testing.T) {
	// A quote that cannot be checked is exactly the kind that must not be shown.
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.Evidence = []Evidence{{
		Kind: EvidenceTranscriptSpan, SupportsClaim: "x",
		Quote: "something", CharStart: ptrI(0), CharEnd: ptrI(9),
	}}

	rc := BuildRenderable(evaluationWith(c), "").Criteria[0]

	if len(claimsOfKind(rc, ClaimEvidence)) != 0 {
		t.Error("a quote was rendered against an empty transcript")
	}
}

// --- measurement evidence ---------------------------------------------------

func TestAMeasurementIsRenderedWithItsValue(t *testing.T) {
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.Evidence = []Evidence{{
		Kind: EvidenceMeasurementRef, SupportsClaim: "speech rate below range",
		MeasurementID: "m.wpm",
	}}
	e := evaluationWith(c)
	e.Provenance.Measurements = []Measurement{
		{ID: "m.wpm", Name: "words per minute", Value: 97, Unit: UnitWordsPerMinute},
	}

	claims := claimsOfKind(BuildRenderable(e, testTranscript).Criteria[0], ClaimEvidence)

	if len(claims) != 1 || claims[0].MeasurementValue != 97 {
		t.Fatalf("measurement not resolved: %+v", claims)
	}
}

func TestAMeasurementNotInProvenanceIsWithheld(t *testing.T) {
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.Evidence = []Evidence{{
		Kind: EvidenceMeasurementRef, SupportsClaim: "x", MeasurementID: "m.invented",
	}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if rc.Withheld[0].Reason != WithholdMeasurementMissing {
		t.Errorf("reason = %q", rc.Withheld[0].Reason)
	}
}

// --- the summary rests on what is underneath it -----------------------------

func TestASummaryWithNoResolvedSupportIsWithheld(t *testing.T) {
	// Prose with nothing underneath it is the most persuasive kind of unfounded
	// claim: it reads as an assessment while resting on nothing checkable.
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.Summary = "You spoke at length with clear organisation."
	c.RubricMatches = []RubricMatch{{DescriptorID: "fc.99"}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(claimsOfKind(rc, ClaimSummary)) != 0 {
		t.Error("an unsupported summary was rendered")
	}
	found := false
	for _, wc := range rc.Withheld {
		if wc.Kind == ClaimSummary && wc.Reason == WithholdNoSupport {
			found = true
		}
	}
	if !found {
		t.Errorf("summary not withheld for lack of support: %+v", rc.Withheld)
	}
}

func TestASummaryIsShownOnceSomethingResolves(t *testing.T) {
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.Summary = "You spoke at length."
	c.RubricMatches = []RubricMatch{{DescriptorID: "fc.6", Polarity: PolaritySupports}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(claimsOfKind(rc, ClaimSummary)) != 1 {
		t.Errorf("supported summary not rendered: %+v", rc.Claims)
	}
}

// --- suppression is visible -------------------------------------------------

func TestWithheldClaimsAreCountedNotSilentlyDropped(t *testing.T) {
	c := scoredCriterion(CriterionFluencyCoherence, 6.0)
	c.RubricMatches = []RubricMatch{{DescriptorID: "fc.99"}, {DescriptorID: "lr.7"}}
	c.Evidence = []Evidence{{
		Kind: EvidenceMeasurementRef, SupportsClaim: "x", MeasurementID: "m.gone",
	}}

	r := BuildRenderable(evaluationWith(c), testTranscript)

	if !r.AnyWithheld() {
		t.Fatal("suppression not surfaced")
	}
	if r.WithheldCount() != 3 {
		t.Errorf("WithheldCount = %d, want 3", r.WithheldCount())
	}
}

// --- partial results and limitations are explicit ---------------------------

func TestAnAbsentOverallBandCarriesAnExplanation(t *testing.T) {
	e := evaluationWith(
		scoredCriterion(CriterionFluencyCoherence, 6.0),
		CriterionResult{
			CriterionID: CriterionLexicalResource, Status: CriterionUnavailable,
			UnavailableReason: ReasonDeadlineExceeded,
		},
	)
	e.Overall.Band = nil

	r := BuildRenderable(e, testTranscript)

	if r.Band != nil {
		t.Error("a band was invented")
	}
	if r.BandWithheldReason == "" {
		t.Fatal("no explanation for the absent band")
	}
	for _, want := range []string{"at least 3", "1 completed"} {
		if !strings.Contains(r.BandWithheldReason, want) {
			t.Errorf("explanation missing %q: %q", want, r.BandWithheldReason)
		}
	}
}

func TestAnUnavailableCriterionShowsNoJustification(t *testing.T) {
	// Rubric citations beside "could not be assessed" would imply an assessment
	// happened.
	c := CriterionResult{
		CriterionID: CriterionPronunciation, Status: CriterionUnavailable,
		UnavailableReason: ReasonInsufficientEvidence,
		Summary:           "Could not be assessed.",
		RubricMatches:     []RubricMatch{{DescriptorID: "pr.6", Polarity: PolaritySupports}},
	}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(rc.Claims) != 0 {
		t.Errorf("an unavailable criterion rendered claims: %+v", rc.Claims)
	}
	if rc.Band != nil {
		t.Error("an unavailable criterion carries a band")
	}
	if rc.UnavailableReason != ReasonInsufficientEvidence {
		t.Errorf("reason lost: %q", rc.UnavailableReason)
	}
}

func TestPronunciationAlwaysCarriesItsLimitation(t *testing.T) {
	// GOA-133: this criterion reasons from recognition confidence and pause
	// structure. A band shown without that caveat claims something the system
	// never measured.
	c := scoredCriterion(CriterionPronunciation, 6.5)
	c.RubricMatches = []RubricMatch{{DescriptorID: "pr.6", Polarity: PolaritySupports}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(rc.Limitations) == 0 {
		t.Fatal("pronunciation rendered with no limitation")
	}
	joined := strings.ToLower(strings.Join(rc.Limitations, " "))
	for _, want := range []string{"individual sound", "intonation"} {
		if !strings.Contains(joined, want) {
			t.Errorf("limitation does not mention %q: %q", want, joined)
		}
	}
}

func TestAnExistingPronunciationLimitationIsNotDuplicated(t *testing.T) {
	c := scoredCriterion(CriterionPronunciation, 6.5)
	c.Limitations = []string{"Does not assess individual sounds or intonation."}
	c.RubricMatches = []RubricMatch{{DescriptorID: "pr.6", Polarity: PolaritySupports}}

	rc := BuildRenderable(evaluationWith(c), testTranscript).Criteria[0]

	if len(rc.Limitations) != 1 {
		t.Errorf("limitation duplicated: %+v", rc.Limitations)
	}
}

// --- provenance a surface cannot drop ---------------------------------------

func TestScoreSemanticsTravelWithTheBand(t *testing.T) {
	// A surface must not be able to render a band without the qualifier.
	r := BuildRenderable(evaluationWith(scoredCriterion(CriterionFluencyCoherence, 6.0)), testTranscript)

	if r.ScoreSemantics != ScoreSemantics {
		t.Errorf("score semantics = %q", r.ScoreSemantics)
	}
	if r.RubricID != RubricID || r.RubricVersion != RubricVersion {
		t.Error("rubric identity not carried to the surface")
	}
}

func TestDescriptorsCitedListsWhatWasActuallyShown(t *testing.T) {
	fluency := scoredCriterion(CriterionFluencyCoherence, 6.0)
	fluency.RubricMatches = []RubricMatch{
		{DescriptorID: "fc.6", Polarity: PolaritySupports},
		{DescriptorID: "fc.99"}, // withheld, so it must not appear
	}
	lexical := scoredCriterion(CriterionLexicalResource, 6.0)
	lexical.RubricMatches = []RubricMatch{{DescriptorID: "lr.6", Polarity: PolaritySupports}}

	got := BuildRenderable(evaluationWith(fluency, lexical), testTranscript).DescriptorsCited()

	if len(got) != 2 || got[0] != "fc.6" || got[1] != "lr.6" {
		t.Errorf("DescriptorsCited() = %v, want [fc.6 lr.6]", got)
	}
}
