package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

type recordingMetrics struct {
	mu         sync.Mutex
	alerts     int
	dailySpend float64
}

func (r *recordingMetrics) RecordUserDailyCostAlert() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.alerts++
}

func (r *recordingMetrics) SetDailySpendUSD(value float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.dailySpend = value
}

func (r *recordingMetrics) snapshot() (int, float64) {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.alerts, r.dailySpend
}

func newTestMonitor(
	t *testing.T,
	threshold float64,
) (*CostMonitor, *miniredis.Miniredis, *recordingMetrics, *bytes.Buffer) {
	t.Helper()

	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() {
		_ = client.Close()
	})

	logBuffer := &bytes.Buffer{}
	logger := zerolog.New(logBuffer)
	metrics := &recordingMetrics{}

	monitor, err := NewCostMonitor(
		client,
		logger,
		metrics,
		testPricing,
		2,
		10,
		threshold,
		time.Minute,
		150,
	)
	if err != nil {
		t.Fatal(err)
	}

	return monitor, server, metrics, logBuffer
}

func decodeAlerts(t *testing.T, logOutput io.Reader) []map[string]any {
	t.Helper()

	alerts := make([]map[string]any, 0)
	for _, line := range strings.Split(strings.TrimSpace(readAll(t, logOutput)), "\n") {
		if line == "" {
			continue
		}
		entry := map[string]any{}
		if err := json.Unmarshal([]byte(line), &entry); err != nil {
			t.Fatalf("log line is not JSON: %q", line)
		}
		if entry["event_type"] == "USER_DAILY_COST_EXCEEDED" {
			alerts = append(alerts, entry)
		}
	}

	return alerts
}

func readAll(t *testing.T, r io.Reader) string {
	t.Helper()
	data, err := io.ReadAll(r)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

// A user whose priced spend crosses the threshold must produce exactly one
// alert carrying the figure that tripped it.
func TestCostMonitorAlertsWhenUserExceedsDailyThreshold(t *testing.T) {
	monitor, server, metrics, logBuffer := newTestMonitor(t, 1.0)
	date := time.Now().UTC().Format(time.DateOnly)

	// 400,000 prompt tokens at $2/1M plus 40,000 completion at $10/1M = $1.20.
	writeCostFixture(t, server, date, "spender", "rag", "claude-opus-4-8", 400_000, 40_000)

	monitor.evaluate(context.Background())

	alertCount, dailySpend := metrics.snapshot()
	if alertCount != 1 {
		t.Fatalf("expected exactly 1 alert, got %d", alertCount)
	}
	if dailySpend != 1.2 {
		t.Fatalf("expected daily spend gauge 1.2, got %v", dailySpend)
	}

	alerts := decodeAlerts(t, logBuffer)
	if len(alerts) != 1 {
		t.Fatalf("expected 1 alert log, got %d", len(alerts))
	}
	if alerts[0]["user_id"] != "spender" {
		t.Fatalf("alert names the wrong user: %v", alerts[0]["user_id"])
	}
	if alerts[0]["user_cost_usd"] != 1.2 {
		t.Fatalf("alert reports the wrong cost: %v", alerts[0]["user_cost_usd"])
	}
	if alerts[0]["severity"] != "HIGH" {
		t.Fatalf("alert is missing its severity: %v", alerts[0]["severity"])
	}
}

// A user sitting under the threshold must stay silent. Without this the test
// above would pass just as well against a monitor that alerts unconditionally.
func TestCostMonitorStaysSilentBelowThreshold(t *testing.T) {
	monitor, server, metrics, logBuffer := newTestMonitor(t, 1.0)
	date := time.Now().UTC().Format(time.DateOnly)

	// $0.90 — real spend, but under the line.
	writeCostFixture(t, server, date, "thrifty", "rag", "claude-opus-4-8", 400_000, 10_000)

	monitor.evaluate(context.Background())

	alertCount, dailySpend := metrics.snapshot()
	if alertCount != 0 {
		t.Fatalf("expected no alert below the threshold, got %d", alertCount)
	}
	if dailySpend != 0.9 {
		t.Fatalf("expected daily spend gauge 0.9, got %v", dailySpend)
	}
	if alerts := decodeAlerts(t, logBuffer); len(alerts) != 0 {
		t.Fatalf("expected no alert log, got %d", len(alerts))
	}
}

// Repeated sweeps of a still-breaching user must not re-alert. A monitor that
// fires every five minutes for the rest of the day trains people to ignore it.
func TestCostMonitorAlertsOncePerUserPerDay(t *testing.T) {
	monitor, server, metrics, logBuffer := newTestMonitor(t, 1.0)
	date := time.Now().UTC().Format(time.DateOnly)

	writeCostFixture(t, server, date, "spender", "rag", "claude-opus-4-8", 400_000, 40_000)

	for i := 0; i < 4; i++ {
		monitor.evaluate(context.Background())
	}

	if alertCount, _ := metrics.snapshot(); alertCount != 1 {
		t.Fatalf("expected 1 alert across 4 sweeps, got %d", alertCount)
	}
	if alerts := decodeAlerts(t, logBuffer); len(alerts) != 1 {
		t.Fatalf("expected 1 alert log across 4 sweeps, got %d", len(alerts))
	}
}

// Spend is attributed per user: one breaching user must not silence or
// implicate another, and each gets its own alert.
func TestCostMonitorAlertsPerUserIndependently(t *testing.T) {
	monitor, server, metrics, logBuffer := newTestMonitor(t, 1.0)
	date := time.Now().UTC().Format(time.DateOnly)

	writeCostFixture(t, server, date, "user-a", "rag", "claude-opus-4-8", 400_000, 40_000)
	writeCostFixture(t, server, date, "user-b", "writing", "claude-opus-4-8", 400_000, 40_000)
	writeCostFixture(t, server, date, "user-c", "rag", "claude-opus-4-8", 1_000, 100)

	monitor.evaluate(context.Background())

	if alertCount, _ := metrics.snapshot(); alertCount != 2 {
		t.Fatalf("expected 2 alerts, got %d", alertCount)
	}

	alerts := decodeAlerts(t, logBuffer)
	if len(alerts) != 2 {
		t.Fatalf("expected 2 alert logs, got %d", len(alerts))
	}
	if alerts[0]["user_id"] != "user-a" || alerts[1]["user_id"] != "user-b" {
		t.Fatalf("wrong users alerted: %v, %v", alerts[0]["user_id"], alerts[1]["user_id"])
	}
}

// Yesterday's spend must not trip today's alert — the roll-up is per UTC day.
func TestCostMonitorIgnoresOtherDays(t *testing.T) {
	monitor, server, metrics, _ := newTestMonitor(t, 1.0)

	writeCostFixture(t, server, "2026-01-01", "spender", "rag", "claude-opus-4-8", 400_000, 40_000)

	monitor.evaluate(context.Background())

	alertCount, dailySpend := metrics.snapshot()
	if alertCount != 0 {
		t.Fatalf("expected no alert for another day's spend, got %d", alertCount)
	}
	if dailySpend != 0 {
		t.Fatalf("expected today's spend to be 0, got %v", dailySpend)
	}
}

// The monitor shares its arithmetic with GET /admin/costs. If they ever
// diverge, the alert threshold measures something an operator cannot see.
func TestCostMonitorAgreesWithAdminCostsEndpoint(t *testing.T) {
	monitor, server, metrics, _ := newTestMonitor(t, 1.0)
	date := time.Now().UTC().Format(time.DateOnly)

	writeCostFixture(t, server, date, "user-a", "rag", "claude-opus-4-8", 400_000, 40_000)
	writeCostFixture(t, server, date, "user-b", "writing", "gpt-5.5", 12_000, 3_000)

	monitor.evaluate(context.Background())
	_, monitorSpend := metrics.snapshot()

	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() {
		_ = client.Close()
	})
	users, err := computeDailyUserCosts(context.Background(), client, date, monitor.prices, 2, 10)
	if err != nil {
		t.Fatal(err)
	}
	endpointSpend := 0.0
	for _, entry := range users {
		endpointSpend += roundUSD(entry.TotalCostUSD)
	}

	if roundUSD(endpointSpend) != monitorSpend {
		t.Fatalf(
			"monitor and endpoint disagree: monitor %v, endpoint %v",
			monitorSpend, roundUSD(endpointSpend),
		)
	}
}

// Run must evaluate immediately rather than waiting out its first interval,
// or a service restarting faster than the interval never checks the budget.
func TestCostMonitorRunEvaluatesBeforeFirstTick(t *testing.T) {
	monitor, server, metrics, _ := newTestMonitor(t, 1.0)
	monitor.interval = time.Hour
	date := time.Now().UTC().Format(time.DateOnly)

	writeCostFixture(t, server, date, "spender", "rag", "claude-opus-4-8", 400_000, 40_000)

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		monitor.Run(ctx)
		close(done)
	}()

	deadline := time.After(2 * time.Second)
	for {
		if alertCount, _ := metrics.snapshot(); alertCount == 1 {
			break
		}
		select {
		case <-deadline:
			cancel()
			t.Fatal("Run did not evaluate before its first tick")
		default:
			time.Sleep(5 * time.Millisecond)
		}
	}

	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Run did not stop when its context was cancelled")
	}
}
