package telemetry

import (
	"context"
	"errors"
	"os"
	"strconv"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog/log"
)

// Daily speaking budget, in seconds. GOA-034 specifies 30 minutes per user per
// day. Zero disables the control, which is how the E2E suite and the GOA-036
// load test run without weakening the shipped default.
const defaultDailySpeakingSeconds = 30 * 60

// Ceiling on every quota round trip. Short on purpose: this control sits on the
// open and close paths of a live WebSocket session, and a slow cache must never
// become a slow product.
const quotaTimeout = 500 * time.Millisecond

// SpeakingQuota meters a resource instead of counting events, which is why it
// could not reuse the Gateway's rate limiter (GOA-034, OWASP LLM04).
//
// Two things make this different from every other limit in GOA:
//
// You cannot increment a counter when the request arrives, because the cost of
// a speaking session is its duration and that is unknown until it ends. So the
// spend is recorded at close and checked at open -- meaning a user can always
// start one session that takes them over budget. Accepted: the alternative is
// cutting someone off mid-sentence, and one session of overrun is cheaper than
// that experience.
//
// And the Gateway never sees this traffic at all. There is no WebSocket proxy
// (BUG-029 / GOA-094), so a speaking session bypasses every Gateway control by
// design. Enforcing here is not a preference, it is the only place the fact
// exists.
type SpeakingQuota struct {
	DailySeconds int
}

// unavailableUntil latches the quota off after a Redis failure.
//
// Without it, an unreachable Redis meant every concurrent session independently
// attempted to dial a host that was not coming back. go-redis retries a failed
// dial with backoff, and its pool keeps goroutines alive past the caller's
// context, so a hundred closing sessions produced a hundred stacked dial
// attempts -- which the speaking service's goroutine-leak test caught
// immediately, and which in production would be a pile-up on the close path at
// exactly the moment a dependency is already struggling.
//
// One failure disables the check for a short window. Losing quota accounting
// while the cache is down is the cheaper failure: speaking runs a local CPU
// model and costs no API spend, so the control is protecting capacity rather
// than money.
var unavailableUntil atomic.Int64

const unavailableBackoff = 30 * time.Second

func quotaAvailable() bool {
	return time.Now().UnixNano() >= unavailableUntil.Load()
}

func markUnavailable(err error) {
	unavailableUntil.Store(time.Now().Add(unavailableBackoff).UnixNano())
	log.Warn().Err(err).
		Dur("backoff", unavailableBackoff).
		Msg("Speaking quota store unavailable; skipping quota checks")
}

// NewSpeakingQuota reads the budget from SPEAKING_SECONDS_PER_DAY and checks
// once, at startup, that the quota store is actually reachable.
//
// The probe is what makes the latch work. A latch alone is set by the first
// failure, which is no help when fifty sessions close at the same instant and
// all fifty are already in flight -- every one of them dials a dead host, and
// go-redis's pool outlives their contexts. Asking once at boot means that in an
// environment without Redis (every test binary, and any deployment where the
// cache is missing) the per-session path never touches the network at all.
//
// After the backoff expires one request will try again, so a Redis that comes
// back is picked up without a restart.
func NewSpeakingQuota() *SpeakingQuota {
	seconds := defaultDailySpeakingSeconds
	if raw := os.Getenv("SPEAKING_SECONDS_PER_DAY"); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil {
			seconds = parsed
		} else {
			log.Warn().Str("value", raw).Msg("Invalid SPEAKING_SECONDS_PER_DAY; using default")
		}
	}

	if redisClient != nil && seconds > 0 {
		ctx, cancel := context.WithTimeout(context.Background(), quotaTimeout)
		defer cancel()
		if err := redisClient.Ping(ctx).Err(); err != nil {
			markUnavailable(err)
		}
	}

	return &SpeakingQuota{DailySeconds: seconds}
}

func quotaKey(userID string, at time.Time) string {
	return "speaking:quota:" + at.Format("2006-01-02") + ":" + userID
}

// Allow reports whether the user may start another session, and how much of
// their budget is already spent.
//
// Fails OPEN when Redis is unreachable, and that is a deliberate split from the
// Gateway's AI limiter, which fails closed. The difference is what failure
// costs: a chat request that slips past a quota buys a billed API call, while a
// speaking session runs a local CPU model and costs no money at all. Refusing
// every user their speaking practice because a cache is down would be the
// larger harm.
func (q *SpeakingQuota) Allow(ctx context.Context, userID string) (bool, int64) {
	if q == nil || q.DailySeconds <= 0 || redisClient == nil || userID == "" || !quotaAvailable() {
		return true, 0
	}

	// Bounded, because this sits between a user and the start of their session.
	// go-redis retries a failed dial five times with backoff, so without a
	// deadline an unreachable Redis turns "check a counter" into seconds of
	// blocking -- and, under concurrency, a pile of goroutines waiting on a
	// host that is not coming back. A load test caught exactly that.
	ctx, cancel := context.WithTimeout(ctx, quotaTimeout)
	defer cancel()

	spent, err := redisClient.Get(ctx, quotaKey(userID, time.Now().UTC())).Int64()
	if err != nil {
		// redis.Nil is the normal first-session-of-the-day case and must not
		// latch the control off; anything else means the store is unhealthy.
		if !errors.Is(err, redis.Nil) {
			markUnavailable(err)
		}
		return true, 0
	}

	return spent < int64(q.DailySeconds), spent
}

// Record adds a finished session's duration to today's total.
//
// Called at close, where the duration is finally known. The key expires after
// two days rather than one: a session that starts at 23:59 UTC records against
// the day it began, and the extra margin keeps that from being lost to a
// same-day expiry.
func (q *SpeakingQuota) Record(ctx context.Context, userID string, seconds float64) {
	if q == nil || q.DailySeconds <= 0 || redisClient == nil || userID == "" || seconds <= 0 || !quotaAvailable() {
		return
	}

	ctx, cancel := context.WithTimeout(ctx, quotaTimeout)
	defer cancel()

	key := quotaKey(userID, time.Now().UTC())
	pipe := redisClient.Pipeline()
	pipe.IncrBy(ctx, key, int64(seconds))
	pipe.Expire(ctx, key, 48*time.Hour)
	if _, err := pipe.Exec(ctx); err != nil {
		// Best effort. Losing one session's accounting is a smaller problem
		// than failing the close path of a session the user already finished.
		markUnavailable(err)
	}
}
