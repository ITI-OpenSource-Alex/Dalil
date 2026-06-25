package observability

import (
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

type Metrics struct {
	RequestsTotal      *prometheus.CounterVec
	LatencySeconds     *prometheus.HistogramVec
	RateLimitHitsTotal *prometheus.CounterVec
	AuthFailuresTotal  prometheus.Counter
}

func NewMetrics() (*Metrics, error) {
	requestsTotal, err := registerCounterVec(
		prometheus.CounterOpts{
			Name: "goa_gateway_requests_total",
			Help: "Total HTTP requests handled by the gateway.",
		},
		[]string{"route", "method", "status_code"},
	)
	if err != nil {
		return nil, err
	}

	latencySeconds, err := registerHistogramVec(
		prometheus.HistogramOpts{
			Name:    "goa_gateway_latency_seconds",
			Help:    "Gateway request latency in seconds.",
			Buckets: []float64{0.05, 0.1, 0.2, 0.5, 1, 5},
		},
		[]string{"route"},
	)
	if err != nil {
		return nil, err
	}

	rateLimitHitsTotal, err := registerCounterVec(
		prometheus.CounterOpts{
			Name: "goa_gateway_rate_limit_hits_total",
			Help: "Total gateway requests blocked by rate limiting.",
		},
		[]string{"user_id"},
	)
	if err != nil {
		return nil, err
	}

	authFailuresTotal, err := registerCounter(
		prometheus.CounterOpts{
			Name: "goa_gateway_auth_failures_total",
			Help: "Total gateway authentication failures.",
		},
	)
	if err != nil {
		return nil, err
	}

	return &Metrics{
		RequestsTotal:      requestsTotal,
		LatencySeconds:     latencySeconds,
		RateLimitHitsTotal: rateLimitHitsTotal,
		AuthFailuresTotal:  authFailuresTotal,
	}, nil
}

func (m *Metrics) RecordRequest(route string, method string, statusCode int, latency time.Duration) {
	if m == nil {
		return
	}

	if m.RequestsTotal != nil {
		m.RequestsTotal.WithLabelValues(route, method, strconv.Itoa(statusCode)).Inc()
	}

	if m.LatencySeconds != nil {
		m.LatencySeconds.WithLabelValues(route).Observe(latency.Seconds())
	}
}

func (m *Metrics) RecordAuthFailure() {
	if m == nil || m.AuthFailuresTotal == nil {
		return
	}

	m.AuthFailuresTotal.Inc()
}

func (m *Metrics) RecordRateLimitHit(userID string) {
	if m == nil || m.RateLimitHitsTotal == nil {
		return
	}

	m.RateLimitHitsTotal.WithLabelValues(userID).Inc()
}

func registerCounterVec(opts prometheus.CounterOpts, labels []string) (*prometheus.CounterVec, error) {
	counter := prometheus.NewCounterVec(opts, labels)
	if err := prometheus.Register(counter); err != nil {
		if alreadyRegistered, ok := err.(prometheus.AlreadyRegisteredError); ok {
			if existing, ok := alreadyRegistered.ExistingCollector.(*prometheus.CounterVec); ok {
				return existing, nil
			}
		}

		return nil, err
	}

	return counter, nil
}

func registerHistogramVec(opts prometheus.HistogramOpts, labels []string) (*prometheus.HistogramVec, error) {
	histogram := prometheus.NewHistogramVec(opts, labels)
	if err := prometheus.Register(histogram); err != nil {
		if alreadyRegistered, ok := err.(prometheus.AlreadyRegisteredError); ok {
			if existing, ok := alreadyRegistered.ExistingCollector.(*prometheus.HistogramVec); ok {
				return existing, nil
			}
		}

		return nil, err
	}

	return histogram, nil
}

func registerCounter(opts prometheus.CounterOpts) (prometheus.Counter, error) {
	counter := prometheus.NewCounter(opts)
	if err := prometheus.Register(counter); err != nil {
		if alreadyRegistered, ok := err.(prometheus.AlreadyRegisteredError); ok {
			if existing, ok := alreadyRegistered.ExistingCollector.(prometheus.Counter); ok {
				return existing, nil
			}
		}

		return nil, err
	}

	return counter, nil
}
