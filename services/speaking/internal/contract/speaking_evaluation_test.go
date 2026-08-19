package contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// SPEAK-EVAL-003 — the Go half of the tri-language contract.
//
// The shared fixtures live in packages/contracts/fixtures/speaking-evaluation
// and are decoded here, by Pydantic in packages/contracts/py, and by TypeScript
// in packages/contracts/ts. All three must agree, because the drift this
// contract replaces was exactly three representations that each looked correct
// on its own.

const fixtureDir = "../../../../packages/contracts/fixtures/speaking-evaluation"

func loadFixture(t *testing.T, name string) []byte {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(fixtureDir, name))
	if err != nil {
		t.Fatalf("reading fixture %s: %v", name, err)
	}
	return data
}

func decodeFixture(t *testing.T, name string) Evaluation {
	t.Helper()
	var e Evaluation
	dec := json.NewDecoder(strings.NewReader(string(loadFixture(t, name))))
	// Unknown fields are a hard error here, not in production. A shared fixture
	// containing a field this struct does not model means the Go representation
	// has fallen behind the schema -- which is the drift this file exists to
	// catch.
	dec.DisallowUnknownFields()
	if err := dec.Decode(&e); err != nil {
		t.Fatalf("decoding %s: %v", name, err)
	}
	return e
}

func TestDecodeCompleteFixture(t *testing.T) {
	e := decodeFixture(t, "valid-complete.json")

	if e.SchemaVersion != SchemaVersion {
		t.Errorf("schema_version = %q, want %q", e.SchemaVersion, SchemaVersion)
	}
	if e.Status != StatusComplete {
		t.Errorf("status = %q, want complete", e.Status)
	}
	if len(e.Criteria) != 4 {
		t.Fatalf("got %d criteria, want 4", len(e.Criteria))
	}
	for _, c := range e.Criteria {
		if !c.Scored() {
			t.Errorf("%s did not score in the complete fixture", c.CriterionID)
		}
	}
	if e.Overall.Band == nil {
		t.Fatal("complete evaluation has no overall band")
	}
	if *e.Overall.Band != 6.5 {
		t.Errorf("overall band = %v, want 6.5", *e.Overall.Band)
	}
	if e.Provenance.LLMModel == "" {
		t.Error("provenance records no model; this is the field that used to be a hardcoded lie")
	}
	if len(e.Provenance.Measurements) == 0 {
		t.Error("no measurements recorded, but criteria reference them")
	}
}

// TestDecodePartialFixture is the important one: it pins the representation of
// "not measured".
func TestDecodePartialFixture(t *testing.T) {
	e := decodeFixture(t, "valid-partial.json")

	if e.Status != StatusPartial {
		t.Errorf("status = %q, want partial", e.Status)
	}

	var scored, unavailable int
	for _, c := range e.Criteria {
		switch c.Status {
		case CriterionScored:
			scored++
		case CriterionUnavailable:
			unavailable++
			if c.Band != nil {
				t.Errorf(
					"%s is unavailable but decoded a band of %v. Band 0.0 is a real "+
						"IELTS value; it must never mean 'not measured' (BUG-055)",
					c.CriterionID, *c.Band,
				)
			}
			if c.UnavailableReason == "" {
				t.Errorf("%s is unavailable with no reason", c.CriterionID)
			}
		}
	}
	if scored != 1 || unavailable != 3 {
		t.Errorf("got %d scored / %d unavailable, want 1 / 3", scored, unavailable)
	}

	// One criterion scored against a threshold of three, so there is no band.
	if e.Overall.Band != nil {
		t.Errorf(
			"overall band %v was computed from 1 criterion; such a band describes "+
				"which agents survived, not the candidate (BUG-040)",
			*e.Overall.Band,
		)
	}

	if e.Telemetry == nil || e.Telemetry.CostUSD != nil {
		t.Error("cost_usd should decode as null, not 0.0, for an unpriced model (GOA-135)")
	}
}

// TestOverallBandKeyIsAbsentNotNull — round-tripping must not turn an absent
// band into an explicit null. A client checking for key presence and one
// checking for a falsy value must both behave.
func TestOverallBandKeyIsAbsentNotNull(t *testing.T) {
	e := decodeFixture(t, "valid-partial.json")

	encoded, err := json.Marshal(e)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var wire map[string]any
	if err := json.Unmarshal(encoded, &wire); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	overall, _ := wire["overall"].(map[string]any)
	if _, present := overall["band"]; present {
		t.Errorf("overall.band is present after round-trip; it must be omitted entirely: %v", overall)
	}

	criteria, _ := wire["criteria"].([]any)
	for _, raw := range criteria {
		c, _ := raw.(map[string]any)
		if c["status"] != "unavailable" {
			continue
		}
		if _, present := c["band"]; present {
			t.Errorf("an unavailable criterion serialised a band key: %v", c)
		}
	}
}

// TestCostUsdSerialisesAsNullNotOmitted — the opposite requirement to band.
//
// An absent cost and a null cost mean the same thing here ("not priced"), but
// the field is deliberately NOT omitempty: a consumer reading cost must see the
// key and understand it was considered, rather than wonder whether this build
// records cost at all.
func TestCostUsdSerialisesAsNull(t *testing.T) {
	e := decodeFixture(t, "valid-partial.json")
	encoded, _ := json.Marshal(e)

	var wire map[string]any
	_ = json.Unmarshal(encoded, &wire)
	telemetry, _ := wire["telemetry"].(map[string]any)

	value, present := telemetry["cost_usd"]
	if !present {
		t.Fatal("cost_usd key is missing")
	}
	if value != nil {
		t.Errorf("cost_usd = %v, want null", value)
	}
}

// --- validation ------------------------------------------------------------

func TestValidateAcceptsTheValidFixtures(t *testing.T) {
	allowed := AllowedDescriptorBands()
	for _, name := range []string{"valid-complete.json", "valid-partial.json"} {
		t.Run(name, func(t *testing.T) {
			e := decodeFixture(t, name)
			// No transcript supplied: offset checks are skipped, every other rule
			// applies. The fixture's quotes are illustrative and not tied to a
			// real transcript.
			if problems := e.Validate("", allowed); len(problems) != 0 {
				for _, p := range problems {
					t.Errorf("unexpected validation failure: %v", p)
				}
			}
		})
	}
}

func TestValidateRejectsBandOnUnavailableCriterion(t *testing.T) {
	e := decodeFixture(t, "valid-partial.json")
	zero := 0.0
	for i := range e.Criteria {
		if e.Criteria[i].Status == CriterionUnavailable {
			e.Criteria[i].Band = &zero
			break
		}
	}

	problems := e.Validate("", AllowedDescriptorBands())
	if !hasError(problems, ErrStatusValue) {
		t.Fatalf("band 0.0 on an unavailable criterion was accepted: %v", problems)
	}
}

func TestValidateRejectsInventedDescriptor(t *testing.T) {
	e := decodeFixture(t, "valid-complete.json")
	e.Criteria[0].RubricMatches[0].DescriptorID = "fc.11"

	problems := e.Validate("", AllowedDescriptorBands())
	if !hasError(problems, ErrUnknownRef) {
		t.Fatalf("an invented descriptor id was accepted: %v", problems)
	}
}

func TestValidateRejectsDescriptorCitedAtTheWrongBand(t *testing.T) {
	e := decodeFixture(t, "valid-complete.json")
	e.Criteria[0].RubricMatches[0].DescriptorBand = 9.0 // fc.6 is band 6

	problems := e.Validate("", AllowedDescriptorBands())
	if !hasError(problems, ErrUnknownRef) {
		t.Fatalf("a descriptor cited at the wrong band was accepted: %v", problems)
	}
}

func TestValidateRejectsUnresolvableMeasurement(t *testing.T) {
	e := decodeFixture(t, "valid-complete.json")
	e.Criteria[0].Measurements = append(e.Criteria[0].Measurements, "m.does_not_exist")

	problems := e.Validate("", AllowedDescriptorBands())
	if !hasError(problems, ErrUnknownRef) {
		t.Fatalf("an unresolvable measurement reference was accepted: %v", problems)
	}
}

// TestValidateRejectsAQuoteThatIsNotInTheTranscript is the single most important
// validator: a paraphrase presented as a quotation is the most persuasive thing
// an explanation can get wrong, because it looks like proof.
func TestValidateRejectsAQuoteThatIsNotInTheTranscript(t *testing.T) {
	transcript := "I would like to talk about a journey that I took last summer."
	start, end := 0, 12

	e := Evaluation{
		SchemaVersion:  SchemaVersion,
		ScoreSemantics: ScoreSemantics,
		Criteria: []CriterionResult{{
			CriterionID: CriterionFluencyCoherence,
			Status:      CriterionScored,
			Band:        f(6.5),
			Evidence: []Evidence{{
				Kind:          EvidenceTranscriptSpan,
				SupportsClaim: "hesitation",
				Quote:         "something the candidate never said",
				CharStart:     &start,
				CharEnd:       &end,
			}},
		}},
		Overall: Overall{
			Band:                f(6.5),
			IncludedCriteria:    []CriterionID{CriterionFluencyCoherence},
			RoundingRule:        RoundingRuleV1,
			MinCriteriaRequired: 1,
		},
	}

	problems := e.Validate(transcript, nil)
	if !hasError(problems, ErrUnknownRef) {
		t.Fatalf("a fabricated quote was accepted: %v", problems)
	}
}

func TestValidateAcceptsAQuoteThatIsInTheTranscript(t *testing.T) {
	transcript := "I would like to talk about a journey that I took last summer."
	start, end := 0, 12 // "I would like"

	e := Evaluation{
		SchemaVersion:  SchemaVersion,
		ScoreSemantics: ScoreSemantics,
		Criteria: []CriterionResult{{
			CriterionID: CriterionFluencyCoherence,
			Status:      CriterionScored,
			Band:        f(6.5),
			Evidence: []Evidence{{
				Kind:          EvidenceTranscriptSpan,
				SupportsClaim: "opening",
				Quote:         transcript[start:end],
				CharStart:     &start,
				CharEnd:       &end,
			}},
		}},
		Overall: Overall{
			Band:                f(6.5),
			IncludedCriteria:    []CriterionID{CriterionFluencyCoherence},
			RoundingRule:        RoundingRuleV1,
			MinCriteriaRequired: 1,
		},
	}

	if problems := e.Validate(transcript, nil); len(problems) != 0 {
		t.Fatalf("a genuine quote was rejected: %v", problems)
	}
}

func TestValidateRejectsABandThatDoesNotFollowFromItsCriteria(t *testing.T) {
	e := decodeFixture(t, "valid-complete.json")
	e.Overall.Band = f(9.0) // criteria average 6.5

	problems := e.Validate("", AllowedDescriptorBands())
	if !hasError(problems, ErrCalculation) {
		t.Fatalf("an overall band unsupported by its criteria was accepted: %v", problems)
	}
}

func TestValidateRejectsABandBelowTheCriteriaThreshold(t *testing.T) {
	e := decodeFixture(t, "valid-partial.json")
	e.Overall.Band = f(6.0) // only one criterion scored, threshold is three

	problems := e.Validate("", AllowedDescriptorBands())
	if !hasError(problems, ErrCalculation) {
		t.Fatalf("a band computed from too few criteria was accepted: %v", problems)
	}
}

func TestValidateRejectsOverclaimedScoreSemantics(t *testing.T) {
	e := decodeFixture(t, "valid-complete.json")
	e.ScoreSemantics = "official_ielts_band"

	problems := e.Validate("", AllowedDescriptorBands())
	if len(problems) == 0 {
		t.Fatal("a result claiming to be an official IELTS band was accepted")
	}
}

// --- rubric ----------------------------------------------------------------

func TestEveryDescriptorIDMatchesTheSchemaPattern(t *testing.T) {
	// The schema constrains descriptor ids with a regex. A descriptor the Go
	// side accepts but the schema rejects would pass validation here and fail at
	// the wire.
	for _, d := range FrozenRubric {
		prefix, ok := DescriptorIDPrefix(d.Criterion)
		if !ok {
			t.Fatalf("%s has no id prefix", d.Criterion)
		}
		if !strings.HasPrefix(d.ID, prefix+".") {
			t.Errorf("descriptor %q does not use the %q prefix for %s", d.ID, prefix, d.Criterion)
		}
	}
}

func TestEveryCriterionHasDescriptors(t *testing.T) {
	for _, c := range CriterionOrder {
		if got := DescriptorsFor(c); len(got) == 0 {
			t.Errorf("%s has no descriptors; the model would have nothing to cite", c)
		}
	}
}

func TestDescriptorsAreOrderedHighestBandFirst(t *testing.T) {
	for _, c := range CriterionOrder {
		ds := DescriptorsFor(c)
		for i := 1; i < len(ds); i++ {
			if ds[i-1].Band < ds[i].Band {
				t.Errorf("%s descriptors are not highest-first: %v before %v", c, ds[i-1].ID, ds[i].ID)
			}
		}
	}
}

func TestRenderedDescriptorsCarryTheirIDs(t *testing.T) {
	rendered := RenderDescriptorsFor(CriterionFluencyCoherence)
	for _, d := range DescriptorsFor(CriterionFluencyCoherence) {
		if !strings.Contains(rendered, "["+d.ID+"]") {
			t.Errorf("rendered rubric omits id %q; the model cannot cite what it was not shown", d.ID)
		}
	}
}

func TestRubricHashIsStableAndContentAddressed(t *testing.T) {
	first := RubricSHA256()
	if len(first) != 64 {
		t.Fatalf("hash is %d chars, want 64", len(first))
	}
	if second := RubricSHA256(); first != second {
		t.Error("rubric hash is not stable across calls")
	}
}

// --- rounding --------------------------------------------------------------

func TestRoundIELTSBand(t *testing.T) {
	for _, tc := range []struct{ in, want float64 }{
		{6.0, 6.0}, {6.2, 6.0}, {6.24, 6.0},
		{6.25, 6.5}, {6.5, 6.5}, {6.74, 6.5},
		{6.75, 7.0}, {6.9, 7.0}, {7.0, 7.0},
		{0.0, 0.0}, {8.875, 9.0},
	} {
		if got := RoundIELTSBand(tc.in); got != tc.want {
			t.Errorf("RoundIELTSBand(%v) = %v, want %v", tc.in, got, tc.want)
		}
	}
}

func TestIsHalfBand(t *testing.T) {
	for _, v := range []float64{0, 0.5, 5, 6.5, 9} {
		if !IsHalfBand(v) {
			t.Errorf("IsHalfBand(%v) = false, want true", v)
		}
	}
	for _, v := range []float64{-0.5, 6.3, 6.25, 9.5, 10} {
		if IsHalfBand(v) {
			t.Errorf("IsHalfBand(%v) = true, want false", v)
		}
	}
}

// --- helpers ---------------------------------------------------------------

func f(v float64) *float64 { return &v }

func hasError(problems []ValidationError, want error) bool {
	for _, p := range problems {
		if p.Err == want {
			return true
		}
	}
	return false
}
