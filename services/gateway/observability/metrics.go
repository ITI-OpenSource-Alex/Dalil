package observability

import (
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

type Metrics struct {
	RequestsTotal              *prometheus.CounterVec
	LatencySeconds             *prometheus.HistogramVec
	RateLimitHitsTotal         prometheus.Counter
	AuthFailuresTotal          prometheus.Counter
	SecurityInputRejectedTotal *prometheus.CounterVec
	UserDailyCostAlertsTotal   prometheus.Counter
	DailySpendUSD              prometheus.Gauge
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

	rateLimitHitsTotal, err := registerCounter(
		prometheus.CounterOpts{
			Name: "goa_gateway_rate_limit_hits_total",
			Help: "Total gateway requests blocked by rate limiting.",
		},
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

	securityInputRejectedTotal, err := registerCounterVec(
		prometheus.CounterOpts{
			Name: "goa_security_input_rejected_total",
			Help: "Requests rejected by an input security control, by reason.",
		},
		[]string{"reason"},
	)
	if err != nil {
		return nil, err
	}

	// GOA-046. Deliberately unlabelled by user: the alert names the user in its
	// structured log, where a high-cardinality string is free. Putting a user id
	// in a Prometheus label would create one time series per user forever, and
	// the metric only ever needs to answer "how often did this fire".
	userDailyCostAlertsTotal, err := registerCounter(
		prometheus.CounterOpts{
			Name: "goa_gateway_user_daily_cost_alerts_total",
			Help: "Times a single user exceeded the daily AI spend threshold.",
		},
	)
	if err != nil {
		return nil, err
	}

	dailySpendUSD, err := registerGauge(
		prometheus.GaugeOpts{
			Name: "goa_gateway_daily_spend_usd",
			Help: "Total AI spend in USD accrued so far on the current UTC day.",
		},
	)
	if err != nil {
		return nil, err
	}

	return &Metrics{
		RequestsTotal:              requestsTotal,
		LatencySeconds:             latencySeconds,
		RateLimitHitsTotal:         rateLimitHitsTotal,
		AuthFailuresTotal:          authFailuresTotal,
		SecurityInputRejectedTotal: securityInputRejectedTotal,
		UserDailyCostAlertsTotal:   userDailyCostAlertsTotal,
		DailySpendUSD:              dailySpendUSD,
	}, nil
}

// RecordUserDailyCostAlert counts one per-user budget breach.
func (m *Metrics) RecordUserDailyCostAlert() {
	if m == nil || m.UserDailyCostAlertsTotal == nil {
		return
	}

	m.UserDailyCostAlertsTotal.Inc()
}

// SetDailySpendUSD publishes the running total for the current UTC day.
func (m *Metrics) SetDailySpendUSD(value float64) {
	if m == nil || m.DailySpendUSD == nil {
		return
	}

	m.DailySpendUSD.Set(value)
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

func (m *Metrics) RecordRateLimitHit(_ string) {
	if m == nil || m.RateLimitHitsTotal == nil {
		return
	}

	m.RateLimitHitsTotal.Inc()
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

func registerGauge(opts prometheus.GaugeOpts) (prometheus.Gauge, error) {
	gauge := prometheus.NewGauge(opts)
	if err := prometheus.Register(gauge); err != nil {
		if alreadyRegistered, ok := err.(prometheus.AlreadyRegisteredError); ok {
			if existing, ok := alreadyRegistered.ExistingCollector.(prometheus.Gauge); ok {
				return existing, nil
			}
		}

		return nil, err
	}

	return gauge, nil
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

// RecordInputRejected counts a request refused by an input control.
//
// The nil checks match every other recorder here: metrics must never be the
// reason a request fails. A monitoring system that can take down the thing it
// monitors is worse than no monitoring.
func (m *Metrics) RecordInputRejected(reason string) {
	if m == nil || m.SecurityInputRejectedTotal == nil {
		return
	}

	m.SecurityInputRejectedTotal.WithLabelValues(reason).Inc()
}
