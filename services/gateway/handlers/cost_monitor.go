package handlers

import (
	"context"
	"encoding/json"
	"sort"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

// CostAlertRecorder receives the Prometheus side of a budget breach.
//
// It is an interface rather than a concrete *observability.Metrics so this file
// does not import the observability package, which already imports nothing from
// handlers. Keeping the dependency one-way avoids an import cycle the moment
// anything in observability wants a handler type.
type CostAlertRecorder interface {
	RecordUserDailyCostAlert()
	SetDailySpendUSD(float64)
}

// CostMonitor watches the per-user daily LLM spend roll-up and raises an alert
// when a single user crosses the configured threshold.
//
// GOA-046 asks for "alert if a single user exceeds $1/day in AI API costs". The
// check runs here, on a timer, rather than inside GET /admin/costs: an alert
// that only fires when an operator happens to open an admin endpoint is not an
// alert, it is a report. The whole point is to learn about a runaway user
// without being asked.
type CostMonitor struct {
	redisClient             *redis.Client
	logger                  zerolog.Logger
	metrics                 CostAlertRecorder
	prices                  map[string]modelPrice
	fallbackPromptPer1M     float64
	fallbackCompletionPer1M float64
	thresholdUSD            float64
	interval                time.Duration
	budgetUSD               float64
}

// alertStateTTL keeps the "already alerted" marker slightly longer than a day
// so a user who breaches just before midnight UTC cannot be re-alerted for the
// same day by a tick that lands just after it.
const alertStateTTL = 26 * time.Hour

func NewCostMonitor(
	redisClient *redis.Client,
	logger zerolog.Logger,
	metrics CostAlertRecorder,
	pricingJSON string,
	fallbackPromptPer1M float64,
	fallbackCompletionPer1M float64,
	thresholdUSD float64,
	interval time.Duration,
	budgetUSD float64,
) (*CostMonitor, error) {
	prices := make(map[string]modelPrice)
	if err := json.Unmarshal([]byte(pricingJSON), &prices); err != nil {
		return nil, err
	}

	return &CostMonitor{
		redisClient:             redisClient,
		logger:                  logger,
		metrics:                 metrics,
		prices:                  prices,
		fallbackPromptPer1M:     fallbackPromptPer1M,
		fallbackCompletionPer1M: fallbackCompletionPer1M,
		thresholdUSD:            thresholdUSD,
		interval:                interval,
		budgetUSD:               budgetUSD,
	}, nil
}

// Run evaluates immediately and then on every tick until ctx is cancelled.
//
// The immediate first pass matters after a restart: without it, a service that
// crash-loops faster than the interval would never once evaluate the budget.
func (m *CostMonitor) Run(ctx context.Context) {
	if m == nil {
		return
	}

	m.evaluate(ctx)

	ticker := time.NewTicker(m.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			m.evaluate(ctx)
		}
	}
}

func (m *CostMonitor) evaluate(ctx context.Context) {
	date := time.Now().UTC().Format(time.DateOnly)

	users, err := computeDailyUserCosts(
		ctx,
		m.redisClient,
		date,
		m.prices,
		m.fallbackPromptPer1M,
		m.fallbackCompletionPer1M,
	)
	if err != nil {
		// A monitor must never be the reason the gateway falls over, and a
		// Redis blip is not a budget event. Log and wait for the next tick.
		m.logger.Error().Err(err).Str("date", date).
			Msg("cost monitor could not read the daily spend roll-up")
		return
	}

	breached := make([]*userCost, 0)
	totalSpend := 0.0
	for _, entry := range users {
		totalSpend += entry.TotalCostUSD
		if entry.TotalCostUSD > m.thresholdUSD {
			breached = append(breached, entry)
		}
	}

	if m.metrics != nil {
		m.metrics.SetDailySpendUSD(roundUSD(totalSpend))
	}

	// Deterministic order keeps the log readable when several users breach in
	// the same pass, and keeps the tests from flaking on map iteration order.
	sort.Slice(breached, func(i, j int) bool {
		return breached[i].UserID < breached[j].UserID
	})

	for _, entry := range breached {
		m.alertOnce(ctx, date, entry, roundUSD(totalSpend))
	}
}

// alertOnce fires at most one alert per user per UTC day.
//
// The de-duplication marker lives in Redis rather than in process memory
// because the gateway runs more than one task: an in-memory set would alert
// once per replica, and would forget everything on deploy. SetNX is the whole
// mechanism — the first replica to claim the key is the one that alerts.
func (m *CostMonitor) alertOnce(
	ctx context.Context,
	date string,
	entry *userCost,
	totalSpend float64,
) {
	key := "llm:cost-alert:" + date + ":user:" + entry.UserID

	claimed, err := m.redisClient.SetNX(ctx, key, "1", alertStateTTL).Result()
	if err != nil {
		m.logger.Error().Err(err).Str("user_id", entry.UserID).
			Msg("cost monitor could not claim the daily alert marker")
		return
	}
	if !claimed {
		return
	}

	if m.metrics != nil {
		m.metrics.RecordUserDailyCostAlert()
	}

	m.logger.Warn().
		Str("event_type", "USER_DAILY_COST_EXCEEDED").
		Str("severity", "HIGH").
		Str("date", date).
		Str("user_id", entry.UserID).
		Float64("user_cost_usd", roundUSD(entry.TotalCostUSD)).
		Float64("threshold_usd", m.thresholdUSD).
		Float64("total_spend_usd", totalSpend).
		Float64("budget_usd", m.budgetUSD).
		Int64("rag_tokens", entry.Breakdown.RAGTokens).
		Int64("writing_tokens", entry.Breakdown.WritingTokens).
		Int64("speaking_tokens", entry.Breakdown.SpeakingTokens).
		Msg("a single user exceeded the daily AI spend threshold")
}
