package speaking

import (
	"bytes"
	"runtime"
	"sync"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/httpx"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// Used solely by the STT call in stt.go. Whisper runs on CPU in the speech
	// sidecar, so transcription time scales with utterance length: 35 seconds of
	// audio measured at 11.4s (GOA-098), which blew straight through the previous
	// 10s budget and failed every non-trivial utterance (BUG-037). IELTS Part 2
	// answers run one to two minutes by design, so the ceiling has to allow for
	// roughly 40s of processing plus headroom -- the exam format sets this
	// number, not a round figure.
	//
	// GOA-032: the transport is now shared with the TTS and AgentRouter clients
	// (internal/httpx), so a session no longer pays a fresh handshake per leg.
	httpClient = httpx.NewClient(120 * time.Second)

	bufferPool = sync.Pool{
		New: func() interface{} {
			return bytes.NewBuffer(make([]byte, 0, 256*1024))
		},
	}

	activeConnectionsMetric = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "goa_speaking_active_connections",
		Help: "Number of active speaking service WebSocket connections",
	})

	// GOA-032. Buckets are the measurement, not decoration. histogram_quantile
	// interpolates *within* a bucket, so every observation landing in +Inf is
	// unbounded above and the quantile pins to the last finite edge. The previous
	// ceiling here was 5000ms while GOA-098 measured 11,400ms on a 35s clip --
	// every real transcription fell into +Inf and this histogram reported a flat,
	// fabricated P95 of 5s forever.
	//
	// (The help text also said "ElevenLabs". There is no ElevenLabs -- BUG-041.)
	transcriptionLatencyMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_transcription_ms",
		Help:    "Latency of local faster-whisper STT sidecar calls in milliseconds",
		Buckets: []float64{500, 1000, 2500, 5000, 10000, 15000, 20000, 30000, 45000, 60000},
	})

	// The SLO is a ratio, so the ratio needs its own histogram -- it cannot be
	// recovered by dividing two separately-aggregated quantiles. P95(a)/P95(b) is
	// not P95(a/b); those are different sessions in the numerator and the
	// denominator. Observing processing_ms/audio_ms per request is the only way
	// the alert expression matches the acceptance criterion.
	transcriptionRatioMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_transcription_ratio",
		Help:    "STT processing time divided by source audio duration (unitless; 0.33 = 1s of processing per 3s of speech)",
		Buckets: []float64{0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0},
	})

	// Same ceiling problem: was capped at 10s against a measured ~77s session.
	e2eLatencyMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_e2e_latency_ms",
		Help:    "End-to-end latency from first audio chunk received to first TTS chunk written to the socket, in milliseconds",
		Buckets: []float64{5000, 10000, 20000, 30000, 45000, 60000, 90000, 120000, 180000},
	})

	// GOA-032: the number the user actually feels once criteria stream. e2e stays
	// as the honest total, but this is what perceived responsiveness is judged on.
	timeToFirstCriterionMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_time_to_first_criterion_ms",
		Help:    "Latency from first audio chunk received to the first per-criterion result frame being queued for the client, in milliseconds",
		Buckets: []float64{2500, 5000, 10000, 15000, 20000, 30000, 45000, 60000, 90000},
	})

	// Labelled by criterion, because "the swarm is slow" is not actionable and
	// "Pronunciation is slow" is. The outcome label matters just as much: a
	// timed-out agent's elapsed time is the deadline, not a measurement, so
	// mixing the two makes P95 converge on swarmEvaluationTimeout by
	// construction.
	criterionCompleteMetric = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "goa_speaking_criterion_complete_ms",
		Help:    "Latency from swarm start to an individual criterion completing, in milliseconds",
		Buckets: []float64{2500, 5000, 10000, 20000, 30000, 45000, 60000, 90000},
	}, []string{"criterion", "outcome"})

	goroutineCountMetric = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "goa_speaking_goroutine_count",
		Help: "Current number of running goroutines",
	})

	sessionsTotalMetric = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "goa_speaking_sessions_total",
		Help: "Total number of completed speaking sessions",
	}, []string{"outcome"})

	// IELTS band scores awarded per criterion.
	AgentBandScoreMetric = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "goa_speaking_agent_band_score",
		Help:    "IELTS band scores awarded by criteria",
		Buckets: []float64{0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0},
	}, []string{"criterion"})

	// Fed from AgentResult.FirstTokenMs. It used to be fed total completion time,
	// so a metric named "first_token" reported something else entirely -- worse
	// than not having it, because a dashboard cannot tell you it is lying.
	LlmFirstTokenMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_llm_first_token_ms",
		Help:    "Latency from LLM request start to first token emitted in milliseconds",
		Buckets: []float64{250, 500, 1000, 2500, 5000, 10000, 20000, 40000, 60000},
	})

	TtsFirstAudioMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_tts_first_audio_ms",
		Help:    "Latency from Piper TTS request start to first audio chunk received in milliseconds",
		Buckets: []float64{50, 100, 250, 500, 1000, 2000, 5000, 10000},
	})

	// Labelled by which budget broke. A single unlabelled counter cannot tell a
	// slow provider from a slow sidecar, which is exactly the distinction this
	// ticket exists to make. Label values come from slo.go, never from a string
	// literal at a call site -- a typo'd label does not error, it silently
	// creates a second time series no alert matches.
	sloViolationsMetric = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "goa_speaking_slo_violations_total",
		Help: "Count of latency budget breaches, labelled by which budget was exceeded",
	}, []string{"budget"})
)

func StartBackgroundTasks() {
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for range ticker.C {
			goroutineCountMetric.Set(float64(runtime.NumGoroutine()))
		}
	}()
}

// GOA-133 — population-level sanity checks on the measured speech features.
//
// These are the signal that the extraction is sane. A band cannot tell you that
// words-per-minute is being computed wrong; a p50 WPM of 400 can, immediately.
var (
	prosodyWordsPerMinute = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_words_per_minute",
		Help:    "Measured speech rate. Natural English speech sits roughly 90-190; a p50 far outside that means the extraction is wrong, not the candidate.",
		Buckets: []float64{40, 60, 80, 100, 120, 140, 160, 180, 220, 300},
	})

	prosodyPauseRatio = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_pause_ratio",
		Help:    "Fraction of speech duration spent in pauses >=0.3s",
		Buckets: []float64{0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7},
	})

	prosodyMeanWordConfidence = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_mean_word_confidence",
		Help:    "Mean per-word recognition confidence, the intelligibility proxy Pronunciation now scores against",
		Buckets: []float64{0.3, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99},
	})

	// Without this, "no prosody" is indistinguishable from "no sessions": both
	// leave the histograms above empty.
	prosodyUnavailableTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "goa_speaking_prosody_unavailable_total",
		Help: "Sessions where the sidecar returned no usable word timings, so Fluency and Pronunciation were scored without measured features",
	})
)

func recordProsodyMetrics(f agents.ProsodyFeatures) {
	prosodyWordsPerMinute.Observe(f.WordsPerMinute)
	prosodyPauseRatio.Observe(f.PauseRatio)
	prosodyMeanWordConfidence.Observe(f.MeanWordConfidence)
}
