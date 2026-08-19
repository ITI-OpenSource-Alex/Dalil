package agents

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/llm"
)

// GOA-134. The holistic path is the FULL-EXAM grading path, and it diverged from
// the contract swarm.go established under GOA-032/BUG-040: a plain float64
// overall_band with no minimum-criteria gate, so one surviving agent out of four
// produces a confident IELTS band that the exam service then persists as the
// candidate's official speaking score.
//
// This file is the fault-injection matrix. A deterministic mock is the right tool
// here and only here: the injected fault IS the subject, so there is nothing a
// real provider would add except flakiness.
//
// Run with GOA_MATRIX_OUT=<path> to emit the matrix as markdown for
// perf/reports/GOA-134-{pre,post}-matrix.md.

// failMode selects how a criterion fails, because the two must stay
// distinguishable and holistic.go used to report both as TimedOut.
type failMode int

const (
	failNone failMode = iota
	failProviderError
	failParseError
	failDeadline
)

// matrixMockClient fails the first `failCount` criteria it is asked about, in a
// fixed order, so a run is reproducible.
type matrixMockClient struct {
	failCriteria map[string]bool
	mode         failMode
}

func (m *matrixMockClient) StreamCompletion(ctx context.Context, systemPrompt, _ string) (llm.CompletionResult, error) {
	criterion := criterionFromSystemPrompt(systemPrompt)
	if m.failCriteria[criterion] {
		switch m.mode {
		case failProviderError:
			return llm.CompletionResult{}, fmt.Errorf("provider rejected the request: 401 unauthorized")
		case failParseError:
			// BUG-057's shape: a valid response that is not the JSON we asked for.
			return llm.CompletionResult{Text: "# Fluency Assessment\n\nThe candidate..."}, nil
		case failDeadline:
			<-ctx.Done()
			return llm.CompletionResult{}, ctx.Err()
		}
	}
	return llm.CompletionResult{
		Text:             `{"band": 7.0, "overall_feedback": "ok", "part_notes": {}, "examples": [], "improvement_tip": "keep going"}`,
		PromptTokens:     10,
		CompletionTokens: 10,
		LatencyMs:        10,
	}, nil
}

func criterionFromSystemPrompt(systemPrompt string) string {
	for _, name := range CriterionOrder {
		if strings.Contains(systemPrompt, name) {
			return name
		}
	}
	return ""
}

// failFirstN builds the fail-set deterministically from CriterionOrder.
func failFirstN(n int) map[string]bool {
	out := map[string]bool{}
	for i := 0; i < n && i < len(CriterionOrder); i++ {
		out[CriterionOrder[i]] = true
	}
	return out
}

type matrixRow struct {
	Completed      int
	BandKeyPresent bool
	BandValue      any
	Status         string
	Partial        bool
	CompletedCount any
}

// runMatrix drives EvaluateHolisticSwarm at every failure count and reports what
// the CLIENT sees -- the serialised JSON, not the Go struct. `omitempty`
// behaviour is the contract; a struct-level assertion would pass while the wire
// format was still wrong.
func runMatrix(t *testing.T, mode failMode) []matrixRow {
	t.Helper()
	rows := make([]matrixRow, 0, 5)

	for failures := 4; failures >= 0; failures-- {
		completed := 4 - failures

		timeout := 2 * time.Second
		if mode == failDeadline {
			// The deadline arm needs a budget short enough to actually elapse.
			timeout = 150 * time.Millisecond
		}
		ctx, cancel := context.WithTimeout(context.Background(), timeout)

		client := &matrixMockClient{failCriteria: failFirstN(failures), mode: mode}
		res, _ := EvaluateHolisticSwarm(ctx, client, "Part 1: hello. Part 2: a story. Part 3: opinions.", nil)
		cancel()

		encoded, err := json.Marshal(res)
		if err != nil {
			t.Fatalf("marshal: %v", err)
		}
		var wire map[string]any
		if err := json.Unmarshal(encoded, &wire); err != nil {
			t.Fatalf("unmarshal: %v", err)
		}

		band, present := wire["overall_band"]
		rows = append(rows, matrixRow{
			Completed:      completed,
			BandKeyPresent: present,
			BandValue:      band,
			Status:         fmt.Sprint(wire["status"]),
			Partial:        wire["partial"] == true,
			CompletedCount: wire["completed_count"],
		})
	}
	return rows
}

func writeMatrix(t *testing.T, title string, rows []matrixRow) {
	t.Helper()
	path := os.Getenv("GOA_MATRIX_OUT")
	if path == "" {
		return
	}
	var b strings.Builder
	b.WriteString("\n### " + title + "\n\n")
	b.WriteString("| Completed criteria | `overall_band` key | value | `status` | `partial` | `completed_count` |\n")
	b.WriteString("|---|---|---|---|---|---|\n")
	sort.Slice(rows, func(i, j int) bool { return rows[i].Completed > rows[j].Completed })
	for _, r := range rows {
		key := "absent"
		if r.BandKeyPresent {
			key = "**present**"
		}
		val := "—"
		if r.BandKeyPresent {
			val = fmt.Sprint(r.BandValue)
		}
		cc := "absent"
		if r.CompletedCount != nil {
			cc = fmt.Sprint(r.CompletedCount)
		}
		b.WriteString(fmt.Sprintf("| %d of 4 | %s | %s | %s | %v | %s |\n",
			r.Completed, key, val, r.Status, r.Partial, cc))
	}
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		t.Fatalf("open matrix out: %v", err)
	}
	defer f.Close()
	if _, err := f.WriteString(b.String()); err != nil {
		t.Fatalf("write matrix: %v", err)
	}
}

// TestHolisticMatrix_ProviderError is the headline: it must match the contract
// swarm.go already implements.
func TestHolisticMatrix_ProviderError(t *testing.T) {
	rows := runMatrix(t, failProviderError)
	writeMatrix(t, "Provider error", rows)

	for _, r := range rows {
		switch {
		case r.Completed >= MinCriteriaForOverallBand:
			if !r.BandKeyPresent {
				t.Errorf("%d completed: overall_band must be present", r.Completed)
			}
		default:
			if r.BandKeyPresent {
				t.Errorf(
					"%d of 4 criteria completed but overall_band is present with value %v. "+
						"A band derived from fewer than %d criteria describes which agents "+
						"survived, not the candidate (GOA-032, BUG-040).",
					r.Completed, r.BandValue, MinCriteriaForOverallBand,
				)
			}
		}
	}
}

func TestHolisticMatrix_ParseError(t *testing.T) {
	rows := runMatrix(t, failParseError)
	writeMatrix(t, "Malformed JSON (BUG-057 shape)", rows)
	for _, r := range rows {
		if r.Completed < MinCriteriaForOverallBand && r.BandKeyPresent {
			t.Errorf("%d completed: overall_band present (%v)", r.Completed, r.BandValue)
		}
	}
}

func TestHolisticMatrix_Deadline(t *testing.T) {
	rows := runMatrix(t, failDeadline)
	writeMatrix(t, "Deadline exceeded", rows)
	for _, r := range rows {
		if r.Completed < MinCriteriaForOverallBand && r.BandKeyPresent {
			t.Errorf("%d completed: overall_band present (%v)", r.Completed, r.BandValue)
		}
	}
}

// TestHolisticReportsCompletedCount — a client cannot render "2 of 4 criteria"
// without it, and its absence is why `partial` was the only signal.
func TestHolisticReportsCompletedCount(t *testing.T) {
	rows := runMatrix(t, failProviderError)
	for _, r := range rows {
		if r.CompletedCount == nil {
			t.Fatalf("%d completed: completed_count missing from the payload", r.Completed)
		}
	}
}

// TestSwarmAndHolisticAgreeOnBandContract is the guard that would have caught the
// original divergence. The two paths must answer the same question the same way.
func TestSwarmAndHolisticAgreeOnBandContract(t *testing.T) {
	for failures := 4; failures >= 0; failures-- {
		completed := 4 - failures

		hCtx, hCancel := context.WithTimeout(context.Background(), 2*time.Second)
		hRes, _ := EvaluateHolisticSwarm(
			hCtx,
			&matrixMockClient{failCriteria: failFirstN(failures), mode: failProviderError},
			"transcript",
			nil,
		)
		hCancel()

		sCtx, sCancel := context.WithTimeout(context.Background(), 2*time.Second)
		sRes, _ := EvaluateSwarm(
			sCtx,
			&streamingMatrixMockClient{failCriteria: failFirstN(failures)},
			"question", "part1", "transcript", testProsody(), nil,
		)
		sCancel()

		holisticPresent := jsonKeyPresent(t, hRes, "overall_band")
		streamingPresent := jsonKeyPresent(t, sRes, "overall_band")

		if holisticPresent != streamingPresent {
			t.Errorf(
				"%d of 4 completed: holistic overall_band present=%v but streaming present=%v. "+
					"Two paths grading the same rubric must not disagree about whether a band exists.",
				completed, holisticPresent, streamingPresent,
			)
		}
	}
}

// streamingMatrixMockClient is the same fault injector shaped for EvaluateSwarm,
// whose agents send a different system prompt set.
type streamingMatrixMockClient struct {
	failCriteria map[string]bool
}

func (m *streamingMatrixMockClient) StreamCompletion(ctx context.Context, systemPrompt, _ string) (llm.CompletionResult, error) {
	if m.failCriteria[criterionFromSystemPrompt(systemPrompt)] {
		return llm.CompletionResult{}, fmt.Errorf("provider rejected the request")
	}
	return llm.CompletionResult{
		Text:             `{"band": 7.0, "feedback": "ok", "examples": []}`,
		PromptTokens:     10,
		CompletionTokens: 10,
		LatencyMs:        10,
	}, nil
}

func jsonKeyPresent(t *testing.T, v any, key string) bool {
	t.Helper()
	encoded, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var wire map[string]any
	if err := json.Unmarshal(encoded, &wire); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	_, present := wire[key]
	return present
}
