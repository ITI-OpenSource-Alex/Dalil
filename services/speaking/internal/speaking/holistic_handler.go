// internal/speaking/holistic_handler.go
package speaking

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/rs/zerolog/log"
)

var (
	holisticEvaluationLatency = promauto.NewHistogram(prometheus.HistogramOpts{
		Name: "goa_speaking_holistic_evaluation_ms",
		Help: "Latency of holistic speaking evaluations",
		// 5s to 90s. The previous 1s-10s linear range topped out below the
		// measured p95 of a single criterion (28.7s, GOA-032), so every real
		// evaluation landed in +Inf and histogram_quantile pinned the reported
		// P95 to 10s forever -- the same defect GOA-032 found in the streaming
		// histograms, in the one handler it did not touch.
		Buckets: []float64{5000, 10000, 20000, 30000, 45000, 60000, 75000, 90000, 120000},
	})

	// Labelled by outcome so a full-exam evaluation that returned a partial
	// result is distinguishable from one that returned a band. Without this the
	// handler emitted latency only, and a run where three of four agents failed
	// looked identical to a clean one.
	holisticEvaluationsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "goa_speaking_holistic_evaluations_total",
		Help: "Holistic speaking evaluations by outcome",
	}, []string{"outcome"}) // scored | partial_unscored | failed

	holisticCompletedCriteria = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_holistic_completed_criteria",
		Help:    "How many of the four criteria produced a score",
		Buckets: []float64{0, 1, 2, 3, 4},
	})
)

// holisticCriteria fixes the order the four swarm agents are traced in, so the
// child spans always read Fluency → Lexical → Grammar → Pronunciation
// regardless of the map iteration order of the swarm result.
var holisticCriteria = []string{
	"Fluency and Coherence",
	"Lexical Resource",
	"Grammatical Range and Accuracy",
	"Pronunciation",
}

// HandleHolisticEvaluation processes the full exam transcript and returns a holistic band score with extended feedback.
func HandleHolisticEvaluation(w http.ResponseWriter, r *http.Request, cfg *Config, llmClient agents.LLMClient, langfuseClient *langfuse.Client) {
	start := time.Now()
	defer func() {
		holisticEvaluationLatency.Observe(float64(time.Since(start).Milliseconds()))
	}()

	var payload struct {
		ConcatenatedTranscript string `json:"concatenated_transcript"`
		UserID                 string `json:"user_id"`
		ExamSessionID          string `json:"exam_session_id"`
		// GOA-133. Optional: the exam service concatenates three parts recorded in
		// separate sessions, so unlike the streaming path there is no single audio
		// stream here to derive features from. When the caller supplies them, the
		// Fluency and Pronunciation agents get the same measured evidence they get
		// on the streaming path; when it does not, the block is omitted and those
		// prompts say so rather than inferring delivery from text.
		DurationS float64       `json:"duration_s"`
		Words     []agents.Word `json:"words"`
	}

	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		http.Error(w, "Invalid JSON payload", http.StatusBadRequest)
		return
	}

	if payload.ConcatenatedTranscript == "" {
		http.Error(w, "concatenated_transcript is required", http.StatusBadRequest)
		return
	}

	if payload.UserID == "" {
		payload.UserID = "anonymous"
	}

	// swarmEvaluationTimeout, not a literal. This was 15s against a measured p95
	// time-to-first-criterion of 28,728ms (GOA-032, 8 real sessions through the
	// Gateway) -- so the whole four-agent swarm was given roughly half the budget
	// one agent needs. Worse here than on the streaming path: holistic grades the
	// concatenated three-part transcript, so its prompts are larger and its
	// completions slower, not faster.
	//
	// The exam service's HTTP client must stay ABOVE this; see
	// services/exam/app/services/speaking_client.py and the invariant test that
	// pins the two together.
	ctx, cancel := context.WithTimeout(r.Context(), swarmEvaluationTimeout)
	ctx = context.WithValue(ctx, "userID", payload.UserID)
	defer cancel()

	var features *agents.ProsodyFeatures
	if f, ok := agents.ComputeProsody(payload.Words, payload.DurationS); ok {
		features = &f
		recordProsodyMetrics(f)
	}

	swarmStart := time.Now()
	res, err := agents.EvaluateHolisticSwarm(ctx, llmClient, payload.ConcatenatedTranscript, features)
	swarmEnd := time.Now()

	holisticCompletedCriteria.Observe(float64(res.CompletedCount))
	switch {
	case err != nil && res.Status == "failed":
		holisticEvaluationsTotal.WithLabelValues("failed").Inc()
	case res.OverallBand == nil:
		// Criteria landed but not enough to aggregate. This is a distinct
		// outcome from both "scored" and "failed", and it is the one that used
		// to be invisible because a band was fabricated for it.
		holisticEvaluationsTotal.WithLabelValues("partial_unscored").Inc()
	default:
		holisticEvaluationsTotal.WithLabelValues("scored").Inc()
	}

	if err != nil && res.Status == "failed" {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Audit the exam evaluation to Langfuse: one root trace carrying the
	// exam_session_id, with a child agent span per rubric criterion. Reuses the
	// same ingestion client as the practice path (client.go) — this is the exam
	// counterpart of that WebSocket trace, not a second tracing system. Done in
	// a detached goroutine so reporting never blocks or fails the HTTP response.
	reportHolisticTrace(langfuseClient, payload.UserID, payload.ExamSessionID, payload.ConcatenatedTranscript, res, swarmStart, swarmEnd)

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(res); err != nil {
		http.Error(w, "Failed to encode response", http.StatusInternalServerError)
	}

}

// reportHolisticTrace emits the Langfuse trace for a completed holistic exam
// evaluation: a root trace tagged with the exam_session_id and four child agent
// spans (one per IELTS criterion). It mirrors the practice path's async,
// detached-context reporting so a slow or failing Langfuse never affects the
// caller.
func reportHolisticTrace(
	client *langfuse.Client,
	userID, examSessionID, transcript string,
	res agents.HolisticSwarmResult,
	swarmStart, swarmEnd time.Time,
) {
	if client == nil {
		return
	}

	go func() {
		detachedCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		traceID := strings.ReplaceAll(uuid.New().String(), "-", "")

		events := make([]langfuse.IngestionEvent, 0, len(res.Dimensions)+1)
		events = append(events, langfuse.IngestionEvent{
			ID:        traceID,
			Type:      "trace",
			Timestamp: swarmStart,
			Body: langfuse.TraceBody{
				ID:        traceID,
				Name:      "speaking_exam_evaluation",
				UserID:    userID,
				SessionID: examSessionID,
				Metadata: map[string]any{
					"exam_session_id": examSessionID,
					"overall_band":    res.OverallBand,
					"partial":         res.Partial,
				},
			},
		})

		for _, criterion := range holisticCriteria {
			dim, ok := res.Dimensions[criterion]
			if !ok {
				continue
			}

			spanID := strings.ReplaceAll(uuid.New().String(), "-", "")[:16]
			metadata := map[string]any{
				"criterion":       criterion,
				"exam_session_id": examSessionID,
				"timed_out":       dim.TimedOut,
			}
			if !dim.TimedOut {
				metadata["band_score"] = dim.Band
			}

			events = append(events, langfuse.IngestionEvent{
				ID:        spanID,
				Type:      "generation",
				Timestamp: swarmStart,
				Body: langfuse.GenerationBody{
					ID:        spanID,
					TraceID:   traceID,
					Name:      criterion,
					StartTime: swarmStart,
					EndTime:   swarmEnd,
					Input:     transcript,
					Output:    dim.OverallFeedback,
					Metadata:  metadata,
				},
			})
		}

		if err := client.SendBatch(detachedCtx, events); err != nil {
			log.Error().Err(err).Str("exam_session_id", examSessionID).Msg("Failed to report holistic exam trace to Langfuse")
		}
	}()
}
