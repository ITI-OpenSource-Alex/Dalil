package agents

import (
	"fmt"
	"strings"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
	"github.com/rs/zerolog/log"
)

// SPEAK-EVAL-003 — rubric grounding.
//
// Every system prompt opens with "You are an expert IELTS Speaking examiner" and
// then describes the criterion in the prompt author's own words. Nothing in the
// prompt is the rubric, and nothing in the response points at it, so a band and
// a paragraph of fluent justification arrive with no way to check whether the
// justification corresponds to any official descriptor. A model that has read a
// great deal about IELTS will produce text that sounds exactly like a band
// descriptor whether or not one applies -- and that is the more persuasive
// failure, because it reads better than a correct citation would.
//
// So the descriptors are supplied WITH ids, and the model is asked to cite them.
// Anything it cites outside the supplied set is dropped by parseRubricMatches
// rather than displayed. That is what turns "please ground your answer in the
// rubric" from an instruction the model may ignore into a property the code
// enforces.
//
// The citation block is additive and optional on purpose. A model that returns
// no rubric_matches behaves exactly as it did before this file existed: the band
// and the feedback are unaffected. Grounding improves an explanation; it must not
// be able to cost a candidate their score.

// rubricInstruction is appended to a criterion's system prompt.
//
// The wording says "only" twice and names the consequence. Stating that
// unlisted ids are discarded is not a threat, it is information the model can
// act on: given the choice between inventing a plausible id and omitting the
// field, it should omit.
const rubricInstruction = `
%s
In ADDITION to the fields above, you MAY include a "rubric_matches" array. Each
entry cites ONE descriptor id from the list above and says what it establishes:

  "rubric_matches": [
    {"descriptor_id": "fc.6", "polarity": "supports", "application": "one sentence on how this candidate meets it"},
    {"descriptor_id": "fc.7", "polarity": "caps_below", "application": "one sentence on what is missing for the next band"}
  ]

polarity is one of:
  "supports"       -- the candidate meets this descriptor
  "caps_below"     -- this descriptor is what the candidate does NOT yet meet, and is why the band is not higher
  "reaches_toward" -- the candidate shows some features of this descriptor but not consistently

Cite ONLY ids that appear in the list above. An id that is not listed is
discarded and the citation is lost, so omit the field rather than invent one.
Prefer at least one "supports" and one "caps_below": a student can act on why
they did not reach the next band, and cannot act on praise alone.

CALIBRATION. Use the whole scale, including 8 and 9. Read the descriptors
literally: band 9 permits content-related hesitation and self-correction, and
band 8 allows occasional repetition and inaccuracy. A score that places every
strong candidate at 7 tells them nothing.`

// GroundedSystemPrompt returns a criterion's system prompt with its frozen
// descriptors and the citation instruction appended.
//
// An unrecognised criterion returns the base prompt unchanged. Failing closed
// here would mean refusing to score, which is a far worse outcome than scoring
// without citations.
func GroundedSystemPrompt(base string, criterion contract.CriterionID) string {
	descriptors := contract.RenderDescriptorsFor(criterion)
	if descriptors == "" {
		return base
	}
	return base + "\n" + fmt.Sprintf(rubricInstruction, descriptors)
}

// groundedPromptFor resolves a wire criterion name and grounds its prompt.
func groundedPromptFor(base, criterionName string) string {
	id, ok := canonicalCriterionID[criterionName]
	if !ok {
		return base
	}
	return GroundedSystemPrompt(base, id)
}

// rawRubricMatch is what the model returns, before any of it is believed.
type rawRubricMatch struct {
	DescriptorID string `json:"descriptor_id"`
	Polarity     string `json:"polarity"`
	Application  string `json:"application"`
}

// validPolarity is the closed set. An unrecognised polarity is not silently
// coerced to "supports": that would turn "this is why you are NOT a 7" into "this
// is why you ARE a 7", which is the one direction the error must not go.
var validPolarity = map[string]contract.Polarity{
	"supports":       contract.PolaritySupports,
	"caps_below":     contract.PolarityCapsBelow,
	"reaches_toward": contract.PolarityReachesToward,
}

// parseRubricMatches resolves model-supplied citations against the frozen
// rubric, discarding anything that does not resolve.
//
// The criterion is checked too, not just the id: "lr.7" is a real descriptor,
// but citing it under Fluency and Coherence is still a fabricated justification.
// A real id used in the wrong place is exactly the kind of error that survives a
// careless check.
func parseRubricMatches(raw []rawRubricMatch, criterion contract.CriterionID) []contract.RubricMatch {
	if len(raw) == 0 {
		return nil
	}

	out := make([]contract.RubricMatch, 0, len(raw))
	seen := make(map[string]bool, len(raw))

	for _, m := range raw {
		id := strings.TrimSpace(m.DescriptorID)

		descriptor, ok := contract.LookupDescriptor(id)
		if !ok {
			log.Warn().
				Str("descriptor_id", id).
				Str("criterion", string(criterion)).
				Msg("Discarded a rubric citation for an id that is not in the frozen rubric")
			continue
		}
		if descriptor.Criterion != criterion {
			log.Warn().
				Str("descriptor_id", id).
				Str("belongs_to", string(descriptor.Criterion)).
				Str("cited_under", string(criterion)).
				Msg("Discarded a rubric citation for a descriptor belonging to another criterion")
			continue
		}

		polarity, ok := validPolarity[strings.TrimSpace(m.Polarity)]
		if !ok {
			log.Warn().
				Str("descriptor_id", id).
				Str("polarity", m.Polarity).
				Msg("Discarded a rubric citation with an unrecognised polarity")
			continue
		}

		// A descriptor cited twice adds nothing and, if the two entries disagree
		// on polarity, produces an explanation that contradicts itself.
		if seen[id] {
			continue
		}
		seen[id] = true

		out = append(out, contract.RubricMatch{
			RubricID:       contract.RubricID,
			RubricVersion:  contract.RubricVersion,
			DescriptorID:   id,
			DescriptorBand: descriptor.Band,
			Polarity:       polarity,
			Application:    m.Application,
		})
	}

	if len(out) == 0 {
		return nil
	}
	return out
}
