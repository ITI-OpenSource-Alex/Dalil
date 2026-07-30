package observability

import (
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

func TestMetricsRegistryContainsRequiredGatewayMetrics(t *testing.T) {
	oldRegisterer := prometheus.DefaultRegisterer
	oldGatherer := prometheus.DefaultGatherer
	registry := prometheus.NewRegistry()
	prometheus.DefaultRegisterer = registry
	prometheus.DefaultGatherer = registry
	t.Cleanup(func() {
		prometheus.DefaultRegisterer = oldRegisterer
		prometheus.DefaultGatherer = oldGatherer
	})

	metrics, err := NewMetrics()
	if err != nil {
		t.Fatalf("NewMetrics returned error: %v", err)
	}

	metrics.RecordRequest("/health", "GET", 200, 25*time.Millisecond)
	metrics.RecordRateLimitHit("user-1")
	metrics.RecordAuthFailure()

	families, err := registry.Gather()
	if err != nil {
		t.Fatalf("failed to gather metrics: %v", err)
	}

	names := make(map[string]bool)
	for _, family := range families {
		names[family.GetName()] = true
		if family.GetName() == "goa_gateway_rate_limit_hits_total" {
			if labels := family.Metric[0].GetLabel(); len(labels) != 0 {
				t.Fatalf("rate-limit counter must not expose user IDs: %+v", labels)
			}
		}
	}

	required := []string{
		"goa_gateway_requests_total",
		"goa_gateway_latency_seconds",
		"goa_gateway_rate_limit_hits_total",
		"goa_gateway_auth_failures_total",
	}
	for _, name := range required {
		if !names[name] {
			t.Fatalf("expected metric %q to be registered", name)
		}
	}
}
