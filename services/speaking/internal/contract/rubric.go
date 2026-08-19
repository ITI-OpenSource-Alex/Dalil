package contract

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strings"
)

// SPEAK-EVAL-003 — the frozen rubric.
//
// Descriptors carry stable ids so a criterion result can cite one and a
// validator can resolve it. Without ids there is no difference between a model
// quoting the rubric and a model inventing something that sounds like it, and
// the second is the more persuasive of the two.
//
// The text is the official IELTS public band descriptors, mirrored from
// evals/rubrics/speaking.md. It is versioned and hashed: a score records which
// rubric produced it, so changing the rubric does not silently reinterpret every
// historical result.
//
// Bands 9 down to 5 only, matching what the eval rubric file carries. A model
// asked to justify a band below 5 has no descriptor to cite and must return
// insufficient_evidence rather than invent one -- which is the correct outcome,
// because this system has never been calibrated at the bottom of the scale.

const (
	RubricID      = "ielts-speaking-public"
	RubricVersion = "2023-06"
)

// Descriptor is one band's definition for one criterion.
type Descriptor struct {
	ID        string
	Criterion CriterionID
	Band      float64
	Text      string
}

// descriptorPrefix maps a criterion to its id prefix. The prefixes are the
// conventional IELTS abbreviations, which makes an id readable in a log line
// without a lookup: "fc.7" is Fluency and Coherence at band 7.
var descriptorPrefix = map[CriterionID]string{
	CriterionFluencyCoherence: "fc",
	CriterionLexicalResource:  "lr",
	CriterionGrammaticalRange: "gra",
	CriterionPronunciation:    "pr",
}

// FrozenRubric is the descriptor set in id order.
var FrozenRubric = []Descriptor{
	{"fc.9", CriterionFluencyCoherence, 9, "Speaks fluently with only rare repetition or self-correction; hesitation is content-related; speaks coherently with fully appropriate cohesive features."},
	{"fc.8", CriterionFluencyCoherence, 8, "Speaks fluently with only occasional repetition or self-correction; hesitation is usually content-search; develops topics coherently and appropriately."},
	{"fc.7", CriterionFluencyCoherence, 7, "Speaks at length without noticeable effort or loss of coherence; may demonstrate language-search hesitation; uses a range of connectives and discourse markers flexibly."},
	{"fc.6", CriterionFluencyCoherence, 6, "Is willing to speak at length, though may lose coherence at times due to hesitation, repetition, or self-correction; uses a range of connectives."},
	{"fc.5", CriterionFluencyCoherence, 5, "Usually maintains flow of speech but uses repetition, self-correction, or slow speech to keep going; produces simple speech fluently."},

	{"lr.9", CriterionLexicalResource, 9, "Uses vocabulary with full flexibility and precision in all topics; uses idiomatic language naturally and accurately."},
	{"lr.8", CriterionLexicalResource, 8, "Uses a wide vocabulary resource readily and flexibly to convey precise meaning; uses less common and idiomatic vocabulary skilfully."},
	{"lr.7", CriterionLexicalResource, 7, "Uses vocabulary resource flexibly to discuss a variety of topics; uses some less common and idiomatic vocabulary with awareness of collocation."},
	{"lr.6", CriterionLexicalResource, 6, "Has a wide enough vocabulary to discuss topics at length and make meaning clear; uses paraphrase successfully."},
	{"lr.5", CriterionLexicalResource, 5, "Manages to talk about familiar topics, but uses vocabulary with limited flexibility; attempts paraphrase with varying success."},

	{"gra.9", CriterionGrammaticalRange, 9, "Uses a full range of structures naturally and appropriately; produces consistently accurate structures apart from minor slips."},
	{"gra.8", CriterionGrammaticalRange, 8, "Uses a wide range of structures flexibly; produces a majority of error-free sentences."},
	{"gra.7", CriterionGrammaticalRange, 7, "Uses a range of complex structures with some flexibility; frequently produces error-free sentences."},
	{"gra.6", CriterionGrammaticalRange, 6, "Uses a mix of simple and complex structures, but with limited flexibility; may make frequent mistakes with complex structures."},
	{"gra.5", CriterionGrammaticalRange, 5, "Produces basic sentence forms with reasonable accuracy; uses a limited range of more complex structures with frequent errors."},

	// Pronunciation descriptors are carried in full because the criterion must
	// be able to say what it is NOT assessing. GOA-133 established that this
	// system reasons from recognition confidence and pause structure, which
	// supports intelligibility and phrasing and says nothing about individual
	// sounds, word stress or intonation. Citing pr.6 therefore means "generally
	// intelligible", not "these sounds were correct", and the criterion's
	// limitations field must say so.
	{"pr.9", CriterionPronunciation, 9, "Uses a full range of pronunciation features with precision and subtlety; effortless to understand."},
	{"pr.8", CriterionPronunciation, 8, "Uses a wide range of pronunciation features; is easy to understand throughout; L1 accent has minimal effect on intelligibility."},
	{"pr.7", CriterionPronunciation, 7, "Shows all the positive features of band 6 and some, but not all, of the positive features of band 8."},
	{"pr.6", CriterionPronunciation, 6, "Uses a range of pronunciation features with mixed control; can generally be understood throughout, though mispronunciation of individual words or sounds reduces clarity at times."},
	{"pr.5", CriterionPronunciation, 5, "Shows all the positive features of band 4 and some, but not all, of the positive features of band 6."},
}

// descriptorIndex is built once; FrozenRubric is a package-level literal and
// never mutated.
var descriptorIndex = func() map[string]Descriptor {
	idx := make(map[string]Descriptor, len(FrozenRubric))
	for _, d := range FrozenRubric {
		idx[d.ID] = d
	}
	return idx
}()

// LookupDescriptor resolves an id. The bool is false for anything not in the
// frozen set, which callers must treat as an invented citation.
func LookupDescriptor(id string) (Descriptor, bool) {
	d, ok := descriptorIndex[id]
	return d, ok
}

// AllowedDescriptorBands is the id -> band map Evaluation.Validate expects.
func AllowedDescriptorBands() map[string]float64 {
	out := make(map[string]float64, len(FrozenRubric))
	for _, d := range FrozenRubric {
		out[d.ID] = d.Band
	}
	return out
}

// DescriptorsFor returns one criterion's descriptors, highest band first, which
// is the order they are presented to the model.
func DescriptorsFor(criterion CriterionID) []Descriptor {
	var out []Descriptor
	for _, d := range FrozenRubric {
		if d.Criterion == criterion {
			out = append(out, d)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Band > out[j].Band })
	return out
}

// RenderDescriptorsFor formats a criterion's descriptors for a prompt.
//
// The ids are shown because the model must cite them, and it can only cite what
// it was given. Anything it returns outside this set is rejected by the
// validator rather than displayed -- which is the mechanism that turns "please
// ground your answer in the rubric" from an instruction into a guarantee.
func RenderDescriptorsFor(criterion CriterionID) string {
	var b strings.Builder
	b.WriteString("OFFICIAL BAND DESCRIPTORS (cite by id; you may not cite any id not listed here):\n")
	for _, d := range DescriptorsFor(criterion) {
		fmt.Fprintf(&b, "  [%s] Band %.0f: %s\n", d.ID, d.Band, d.Text)
	}
	return b.String()
}

// RubricSHA256 hashes the frozen descriptor set.
//
// Stored in provenance so a result records which rubric produced it. Computed
// from the ids and text rather than from the source file, because the file could
// be reformatted without changing a single descriptor and the hash should track
// meaning, not whitespace.
func RubricSHA256() string {
	h := sha256.New()
	for _, d := range FrozenRubric {
		fmt.Fprintf(h, "%s|%.1f|%s\n", d.ID, d.Band, d.Text)
	}
	return hex.EncodeToString(h.Sum(nil))
}

// DescriptorIDPrefix exposes the id prefix for a criterion, so a caller can
// build or check an id without duplicating the mapping.
func DescriptorIDPrefix(criterion CriterionID) (string, bool) {
	p, ok := descriptorPrefix[criterion]
	return p, ok
}
