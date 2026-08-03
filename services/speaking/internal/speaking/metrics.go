package speaking

import (
	"bytes"
	"net/http"
	"runtime"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// Used solely by the STT call in stt.go. Whisper runs on CPU in the speech
	// sidecar, so transcription time scales with utterance length: 35 seconds of
	// audio measured at 11.4s, which blew straight through the previous 10s
	// budget and failed every non-trivial utterance (BUG-037). IELTS Part 2
	// answers run one to two minutes by design, so the ceiling has to allow for
	// roughly 40s of processing plus headroom -- the exam format sets this
	// number, not a round figure.
	httpClient = &http.Client{
		Timeout: 120 * time.Second,
		Transport: &http.Transport{
			MaxIdleConns:        100,
			MaxIdleConnsPerHost: 100,
			IdleConnTimeout:     90 * time.Second,
		},
	}

	bufferPool = sync.Pool{
		New: func() interface{} {
			return bytes.NewBuffer(make([]byte, 0, 256*1024))
		},
	}

	activeConnectionsMetric = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "goa_speaking_active_connections",
		Help: "Number of active speaking service WebSocket connections",
	})

	transcriptionLatencyMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_transcription_ms",
		Help:    "Latency of ElevenLabs STT transcription calls in milliseconds",
		Buckets: []float64{100, 250, 500, 1000, 1500, 2000, 3000, 5000},
	})

	e2eLatencyMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_e2e_latency_ms",
		Help:    "End-to-end latency from first audio chunk received to first TTS chunk sent in milliseconds",
		Buckets: []float64{200, 500, 1000, 1500, 2000, 2500, 3000, 5000, 10000},
	})

	goroutineCountMetric = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "goa_speaking_goroutine_count",
		Help: "Current number of running goroutines",
	})

	sessionsTotalMetric = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "goa_speaking_sessions_total",
		Help: "Total number of completed speaking sessions",
	}, []string{"outcome"})

	// 1. IELTS Band scores awarded by criteria
	AgentBandScoreMetric = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "goa_speaking_agent_band_score",
		Help:    "IELTS band scores awarded by criteria",
		Buckets: []float64{0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0},
	}, []string{"criterion"})

	// 2. LLM Time to First Token
	LlmFirstTokenMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_llm_first_token_ms",
		Help:    "Latency from LLM request start to first token emitted in milliseconds",
		Buckets: []float64{100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000},
	})

	// 3. ElevenLabs TTS Time to First Audio chunk
	TtsFirstAudioMetric = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "goa_speaking_tts_first_audio_ms",
		Help:    "Latency from TTS request start to first audio chunk generated in milliseconds",
		Buckets: []float64{50, 100, 200, 300, 500, 750, 1000, 2000, 3000},
	})
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
