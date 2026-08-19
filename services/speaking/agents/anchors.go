package agents

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
	"github.com/rs/zerolog/log"
)

// SPEAK-EVAL-007 — band anchors (few-shot calibration).
//
// The measured problem: the scorer ranks candidates well (Spearman 0.86) and
// places the whole scale roughly a band low. Descriptors alone have not fixed
// it, because a descriptor is abstract -- "uses a wide range of structures
// flexibly" does not tell a model what a band 9 answer actually reads like.
// Showing two or three answers at known bands is the standard remedy for a
// systematic offset, and unlike a post-hoc constant it can generalise.
//
// Three constraints shape this file, and all three are about restraint.
//
// RIGHTS. The only officially banded transcripts available are published by the
// IELTS Partners, and their permission status is `pending` -- nobody has read
// the terms. Anchors are therefore loaded from disk at RUNTIME and never
// compiled in, never committed, and never enabled by default. Baking third-party
// text into a binary that ships is a heavier commitment than using it for a
// benchmark number, and it is the wrong way round to do the heavier one first.
//
// LEAKAGE. An anchor must never come from an item that will be scored. Anchoring
// on an answer and then grading it measures memorisation. The manifest's splits
// exist for exactly this, so anchors are drawn from `dev` and the loader refuses
// to serve an anchor whose item id matches the item being scored.
//
// HONESTY. Anchors change the production prompt, so a score produced with them
// is not comparable to one produced without. The set in use is content-hashed
// into provenance, so two runs can be told apart after the fact.

// AnchorSet is the loaded, validated anchor material for one criterion.
type AnchorSet struct {
	Criterion contract.CriterionID
	Examples  []Anchor
}

// Anchor is one banded answer.
type Anchor struct {
	ItemID     string  `json:"item_id"`
	Band       float64 `json:"band"`
	Transcript string  `json:"transcript"`
	// Why this answer earns this band, in the rubric's terms. Optional: without
	// it the model infers the reason, which is weaker but still anchors the
	// scale.
	Rationale string `json:"rationale,omitempty"`
}

// anchorsEnabled gates the whole mechanism.
//
// Default off. An eval that silently changes the production prompt is not
// measuring production, and a rights question that is unresolved should fail
// closed rather than quietly ship.
func anchorsEnabled() bool {
	return strings.EqualFold(os.Getenv("SPEAKING_BAND_ANCHORS"), "true")
}

// AnchorDir is where runtime anchor material is read from. Gitignored.
func AnchorDir() string {
	if dir := os.Getenv("SPEAKING_BAND_ANCHOR_DIR"); dir != "" {
		return dir
	}
	return filepath.Join("evals", "speaking", "anchors")
}

// LoadAnchors reads the anchor set for a criterion, excluding any anchor drawn
// from the item currently being scored.
//
// Returns an empty set rather than an error when anchoring is disabled or no
// material is present: a missing anchor file must degrade to the current
// behaviour, not refuse to score a candidate.
func LoadAnchors(criterion contract.CriterionID, excludeItemID string) AnchorSet {
	set := AnchorSet{Criterion: criterion}
	if !anchorsEnabled() {
		return set
	}

	path := filepath.Join(AnchorDir(), string(criterion)+".json")
	raw, err := os.ReadFile(path)
	if err != nil {
		if !os.IsNotExist(err) {
			log.Warn().Err(err).Str("path", path).Msg("Could not read band anchors")
		}
		return set
	}

	var loaded []Anchor
	if err := json.Unmarshal(raw, &loaded); err != nil {
		log.Warn().Err(err).Str("path", path).Msg("Band anchor file is not valid JSON")
		return set
	}

	for _, anchor := range loaded {
		// The leakage guard. Anchoring on the item being graded measures whether
		// the model can copy a number it was just shown.
		if anchor.ItemID != "" && anchor.ItemID == excludeItemID {
			log.Warn().
				Str("item_id", anchor.ItemID).
				Msg("Skipped a band anchor drawn from the item being scored")
			continue
		}
		if !contract.IsHalfBand(anchor.Band) || strings.TrimSpace(anchor.Transcript) == "" {
			continue
		}
		set.Examples = append(set.Examples, anchor)
	}

	// Ascending, so the model sees the scale climb rather than a jumble. The
	// ordering is the calibration signal as much as the individual examples are.
	sort.Slice(set.Examples, func(i, j int) bool {
		return set.Examples[i].Band < set.Examples[j].Band
	})
	return set
}

// Render formats the anchors for a system prompt. Empty when there are none, so
// the caller can concatenate unconditionally.
func (a AnchorSet) Render() string {
	if len(a.Examples) == 0 {
		return ""
	}

	var b strings.Builder
	b.WriteString("\nCALIBRATION EXAMPLES. Real answers with the band a certified examiner awarded.\n")
	b.WriteString("Use them to locate the scale. They are reference points, not a template:\n")
	b.WriteString("do not reward an answer for resembling one, and do not penalise it for differing.\n\n")

	for _, anchor := range a.Examples {
		fmt.Fprintf(&b, "--- Awarded band %.1f ---\n%s\n", anchor.Band, anchor.Transcript)
		if anchor.Rationale != "" {
			fmt.Fprintf(&b, "Examiner's reasoning: %s\n", anchor.Rationale)
		}
		b.WriteString("\n")
	}
	return b.String()
}

// Fingerprint identifies the anchor set in provenance.
//
// A score produced with anchors is not comparable to one produced without, and
// the two are otherwise indistinguishable in a report. Recording which set was
// in use is what lets a later reader tell them apart.
func (a AnchorSet) Fingerprint() string {
	if len(a.Examples) == 0 {
		return "none"
	}
	ids := make([]string, 0, len(a.Examples))
	for _, anchor := range a.Examples {
		ids = append(ids, fmt.Sprintf("%s@%.1f", anchor.ItemID, anchor.Band))
	}
	return strings.Join(ids, ",")
}
