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
	httpClient = &http.Client{
		Timeout: 10 * time.Second,
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
		Help:    "End-to-end latency from first audio chunk received to transcript sent in milliseconds",
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
