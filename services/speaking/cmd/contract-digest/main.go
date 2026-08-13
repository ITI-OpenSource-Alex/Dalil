// Command contract-digest emits the Go implementation's view of a speaking
// evaluation fixture, in the normalised form defined by
// packages/contracts/conformance/README.md.
//
// It exists so the tri-language conformance driver can diff Go against Python
// and TypeScript. It is a test tool, not a service entrypoint: it reads a
// fixture path, writes the digest to stdout and exits non-zero only if it
// cannot read the file at all.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: contract-digest <fixture.json>")
		os.Exit(2)
	}

	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "contract-digest: %v\n", err)
		os.Exit(2)
	}

	var out strings.Builder
	if digest(raw, &out) {
		fmt.Print(out.String())
		return
	}
	// Rejected. The digest is deliberately just the verdict; the reason goes to
	// stderr for a human debugging a failure, and is not compared, because the
	// three implementations legitimately reject at different stages.
	fmt.Print("verdict=rejected\n")
}

// digest writes the accepted-fixture digest and reports whether the payload was
// accepted. Any decode or validation failure means rejected.
func digest(raw []byte, out *strings.Builder) bool {
	// DisallowUnknownFields matters here: a field the Go types do not know about
	// is drift, and silently dropping it is how the three representations
	// diverged in the first place.
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()

	var e contract.Evaluation
	if err := dec.Decode(&e); err != nil {
		fmt.Fprintf(os.Stderr, "go: decode rejected: %v\n", err)
		return false
	}

	// The transcript is not carried in the fixture, so quote offsets cannot be
	// resolved against it here. Passing the empty string would make every
	// transcript_span fail for the wrong reason, so quote resolution is checked
	// by the Go unit tests and skipped by the conformance run; what is compared
	// across languages is structural agreement.
	problems := e.Validate("", contract.AllowedDescriptorBands())
	if len(problems) > 0 {
		for _, p := range problems {
			fmt.Fprintf(os.Stderr, "go: %s\n", p.Error())
		}
		return false
	}

	w := func(format string, args ...any) { fmt.Fprintf(out, format+"\n", args...) }

	w("verdict=accepted")
	w("schema_version=%s", e.SchemaVersion)
	w("evaluation_id=%s", e.EvaluationID)
	w("mode=%s", e.Mode)
	w("status=%s", e.Status)
	w("score_semantics=%s", e.ScoreSemantics)
	w("criteria_count=%d", len(e.Criteria))

	var scored []float64
	for i, c := range e.Criteria {
		p := fmt.Sprintf("criterion[%d]", i)
		w("%s.criterion_id=%s", p, c.CriterionID)
		w("%s.status=%s", p, c.Status)
		w("%s.band=%s", p, optFloat(c.Band))
		w("%s.unavailable_reason=%s", p, optString(string(c.UnavailableReason)))
		w("%s.rubric_match_ids=%s", p, joinDescriptorIDs(c.RubricMatches))
		w("%s.evidence_kinds=%s", p, joinEvidenceKinds(c.Evidence))
		w("%s.measurements=%s", p, joinStrings(c.Measurements))
		w("%s.limitations_count=%d", p, len(c.Limitations))
		w("%s.improvement_actions_count=%d", p, len(c.ImprovementActions))
		if c.Scored() && c.Band != nil {
			scored = append(scored, *c.Band)
		}
	}

	w("scored_count=%d", len(scored))
	w("min_criteria_required=%d", e.Overall.MinCriteriaRequired)
	w("overall.band=%s", optFloat(e.Overall.Band))
	w("overall.unrounded_mean=%s", optFloat(e.Overall.UnroundedMean))
	w("overall.included=%s", joinCriterionIDs(e.Overall.IncludedCriteria))
	w("overall.excluded=%s", joinCriterionIDs(e.Overall.ExcludedCriteria))
	w("overall.rounding_rule=%s", e.Overall.RoundingRule)

	// Recomputed rather than echoed. If Go, Python and TypeScript ever disagree
	// about half-band rounding, these two lines are where it shows up.
	thresholdMet := len(scored) >= e.Overall.MinCriteriaRequired
	w("derived.threshold_met=%t", thresholdMet)
	if thresholdMet && len(scored) > 0 {
		sum := 0.0
		for _, b := range scored {
			sum += b
		}
		mean := sum / float64(len(scored))
		w("derived.mean_of_scored=%.4f", mean)
		w("derived.rounded_band=%.4f", contract.RoundIELTSBand(mean))
	} else {
		w("derived.mean_of_scored=absent")
		w("derived.rounded_band=absent")
	}

	w("provenance.rubric_id=%s", e.Provenance.RubricID)
	w("provenance.rubric_version=%s", e.Provenance.RubricVersion)
	w("provenance.scorer_version=%s", e.Provenance.ScorerVersion)
	w("provenance.llm_model=%s", optString(e.Provenance.LLMModel))
	w("provenance.audio_format=%s", optString(e.Provenance.AudioFormat))
	w("provenance.measurement_ids=%s", joinMeasurementIDs(e.Provenance.Measurements))

	if e.Telemetry == nil {
		w("telemetry.present=false")
		w("telemetry.cost_usd=absent")
	} else {
		w("telemetry.present=true")
		w("telemetry.cost_usd=%s", optFloat(e.Telemetry.CostUSD))
	}

	w("validation_problems=0")
	return true
}

// optFloat is the whole point of the digest. "absent" and "0.0000" are
// different strings, so an implementation that collapses them changes the
// output and fails the diff.
func optFloat(v *float64) string {
	if v == nil {
		return "absent"
	}
	return fmt.Sprintf("%.4f", *v)
}

func optString(s string) string {
	if s == "" {
		return "absent"
	}
	return s
}

func joinStrings(xs []string) string {
	if len(xs) == 0 {
		return "-"
	}
	return strings.Join(xs, ",")
}

func joinCriterionIDs(xs []contract.CriterionID) string {
	out := make([]string, 0, len(xs))
	for _, x := range xs {
		out = append(out, string(x))
	}
	return joinStrings(out)
}

func joinDescriptorIDs(ms []contract.RubricMatch) string {
	out := make([]string, 0, len(ms))
	for _, m := range ms {
		out = append(out, m.DescriptorID)
	}
	return joinStrings(out)
}

func joinEvidenceKinds(es []contract.Evidence) string {
	out := make([]string, 0, len(es))
	for _, e := range es {
		out = append(out, string(e.Kind))
	}
	return joinStrings(out)
}

// Measurement ids are sorted: they are a set, and the three implementations
// have no reason to agree on the order a set was written in.
func joinMeasurementIDs(ms []contract.Measurement) string {
	out := make([]string, 0, len(ms))
	for _, m := range ms {
		out = append(out, m.ID)
	}
	sort.Strings(out)
	return joinStrings(out)
}
