package agents

import (
	"strings"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
)

// The model can only cite what it was given, so the descriptors have to be in
// the prompt with their ids visible.
func TestGroundedPromptSuppliesTheDescriptorIDs(t *testing.T) {
	prompt := GroundedSystemPrompt(FluencySystemPrompt, contract.CriterionFluencyCoherence)

	if !strings.Contains(prompt, FluencySystemPrompt) {
		t.Error("grounding dropped the original criterion instructions")
	}
	for _, id := range []string{"fc.9", "fc.8", "fc.7", "fc.6", "fc.5"} {
		if !strings.Contains(prompt, "["+id+"]") {
			t.Errorf("descriptor id %s is not in the prompt; the model cannot cite it", id)
		}
	}
	if !strings.Contains(prompt, "rubric_matches") {
		t.Error("the prompt never asks for citations")
	}
	if !strings.Contains(prompt, "caps_below") {
		t.Error("caps_below is missing; without it an explanation cannot answer \"why not a 7\"")
	}

	// Another criterion's descriptors must not leak in, or the model will cite
	// them and parseRubricMatches will silently discard the lot.
	for _, foreign := range []string{"[lr.", "[gra.", "[pr."} {
		if strings.Contains(prompt, foreign) {
			t.Errorf("the fluency prompt contains %s descriptors", foreign)
		}
	}
}

func TestEveryCriterionGetsItsOwnDescriptors(t *testing.T) {
	prompts := map[contract.CriterionID]string{
		contract.CriterionFluencyCoherence: FluencySystemPrompt,
		contract.CriterionLexicalResource:  LexicalSystemPrompt,
		contract.CriterionGrammaticalRange: GrammarSystemPrompt,
		contract.CriterionPronunciation:    PronunciationSystemPrompt,
	}
	for id, base := range prompts {
		t.Run(string(id), func(t *testing.T) {
			grounded := GroundedSystemPrompt(base, id)
			if len(grounded) <= len(base) {
				t.Fatalf("no descriptors were appended for %s", id)
			}
			for _, d := range contract.DescriptorsFor(id) {
				if !strings.Contains(grounded, d.ID) {
					t.Errorf("%s is missing from its own prompt", d.ID)
				}
			}
		})
	}
}

// Both live paths must be grounded through the same helper. A criterion name
// that does not resolve returns the prompt unchanged rather than refusing to
// score: no citations is a worse explanation, no score is a worse product.
func TestGroundedPromptForResolvesTheWireNames(t *testing.T) {
	for _, name := range CriterionOrder {
		grounded := groundedPromptFor("BASE", name)
		if grounded == "BASE" {
			t.Errorf("%q was not grounded", name)
		}
	}
	if got := groundedPromptFor("BASE", "Some Criterion We Do Not Score"); got != "BASE" {
		t.Error("an unknown criterion should pass the prompt through untouched")
	}
}

// The check that makes the citation worth showing.
func TestInventedCitationsAreDiscarded(t *testing.T) {
	cases := []struct {
		name      string
		raw       []rawRubricMatch
		criterion contract.CriterionID
		wantIDs   []string
	}{
		{
			name: "a real descriptor is kept",
			raw: []rawRubricMatch{
				{DescriptorID: "fc.6", Polarity: "supports", Application: "speaks at length"},
			},
			criterion: contract.CriterionFluencyCoherence,
			wantIDs:   []string{"fc.6"},
		},
		{
			name: "an id that is not in the rubric is dropped",
			raw: []rawRubricMatch{
				{DescriptorID: "fc.6", Polarity: "supports"},
				{DescriptorID: "fc.11", Polarity: "supports"},
				{DescriptorID: "fluency.excellent", Polarity: "supports"},
			},
			criterion: contract.CriterionFluencyCoherence,
			wantIDs:   []string{"fc.6"},
		},
		{
			// A real id in the wrong place. This is the citation most likely to
			// survive a careless check, because the id resolves.
			name: "a real descriptor from another criterion is dropped",
			raw: []rawRubricMatch{
				{DescriptorID: "lr.7", Polarity: "supports"},
				{DescriptorID: "fc.7", Polarity: "caps_below"},
			},
			criterion: contract.CriterionFluencyCoherence,
			wantIDs:   []string{"fc.7"},
		},
		{
			// Coercing this to "supports" would turn "why you are NOT a 7" into
			// "why you ARE a 7".
			name: "an unrecognised polarity is dropped, not coerced",
			raw: []rawRubricMatch{
				{DescriptorID: "fc.6", Polarity: "definitely"},
				{DescriptorID: "fc.7", Polarity: "caps_below"},
			},
			criterion: contract.CriterionFluencyCoherence,
			wantIDs:   []string{"fc.7"},
		},
		{
			name: "a duplicate citation is collapsed",
			raw: []rawRubricMatch{
				{DescriptorID: "gra.7", Polarity: "supports"},
				{DescriptorID: "gra.7", Polarity: "caps_below"},
			},
			criterion: contract.CriterionGrammaticalRange,
			wantIDs:   []string{"gra.7"},
		},
		{
			name:      "nothing cited is nil, not an empty slice",
			raw:       nil,
			criterion: contract.CriterionPronunciation,
			wantIDs:   nil,
		},
		{
			name: "everything invented leaves nothing",
			raw: []rawRubricMatch{
				{DescriptorID: "pr.99", Polarity: "supports"},
			},
			criterion: contract.CriterionPronunciation,
			wantIDs:   nil,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := parseRubricMatches(tc.raw, tc.criterion)

			if len(got) != len(tc.wantIDs) {
				t.Fatalf("kept %d citations, want %d: %+v", len(got), len(tc.wantIDs), got)
			}
			for i, want := range tc.wantIDs {
				if got[i].DescriptorID != want {
					t.Errorf("citation %d: %s, want %s", i, got[i].DescriptorID, want)
				}
				// The band comes from the frozen rubric, not from the model. A
				// model-supplied band on a descriptor would be a second, unchecked
				// score hiding inside the explanation.
				descriptor, _ := contract.LookupDescriptor(want)
				if got[i].DescriptorBand != descriptor.Band {
					t.Errorf("%s: band %.1f, want the frozen %.1f",
						want, got[i].DescriptorBand, descriptor.Band)
				}
				if got[i].RubricID != contract.RubricID || got[i].RubricVersion != contract.RubricVersion {
					t.Errorf("%s: citation does not record which rubric it came from", want)
				}
			}
		})
	}
}

// Whatever the model returns, the citations that survive must satisfy the
// contract's validator -- the same check the tri-language harness applies.
func TestSurvivingCitationsValidateAgainstTheContract(t *testing.T) {
	raw := []rawRubricMatch{
		{DescriptorID: "fc.6", Polarity: "supports", Application: "willing to speak at length"},
		{DescriptorID: "fc.7", Polarity: "caps_below", Application: "hesitation is still noticeable"},
		{DescriptorID: "fc.42", Polarity: "supports", Application: "invented"},
		{DescriptorID: "lr.6", Polarity: "supports", Application: "wrong criterion"},
	}
	matches := parseRubricMatches(raw, contract.CriterionFluencyCoherence)

	band := 6.5
	eval := contract.Evaluation{
		SchemaVersion:  contract.SchemaVersion,
		EvaluationID:   "eval-citations",
		Mode:           contract.ModePractice,
		Status:         contract.StatusPartial,
		ScoreSemantics: contract.ScoreSemantics,
		Criteria: []contract.CriterionResult{{
			CriterionID:   contract.CriterionFluencyCoherence,
			Status:        contract.CriterionScored,
			Band:          &band,
			RubricMatches: matches,
		}},
		Overall: contract.Overall{
			IncludedCriteria:    []contract.CriterionID{contract.CriterionFluencyCoherence},
			RoundingRule:        contract.RoundingRuleV1,
			MinCriteriaRequired: MinCriteriaForOverallBand,
		},
		Provenance: contract.Provenance{
			ScorerVersion: "speaking@test",
			RubricID:      contract.RubricID,
			RubricVersion: contract.RubricVersion,
		},
	}

	for _, problem := range eval.Validate("", contract.AllowedDescriptorBands()) {
		t.Errorf("surviving citations failed validation: %s", problem.Error())
	}
}
