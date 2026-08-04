package speaking

import (
	"github.com/rs/zerolog/log"
)

// sloBudget names one latency budget and its ceiling.
//
// The label value is the contract with Prometheus -- it is what an alert rule
// and a dashboard panel select on -- so it is defined here once and never
// spelled out again at a call site.
type sloBudget struct {
	label string
	limit float64
}

// GOA-032 budgets, set from a measured distribution rather than from round
// numbers. They are figures from one machine, not a contract: re-measure after
// any change to the swarm or the sidecar and restate them here AND in the
// ticket.
//
// Transcription is a RATIO, not an absolute. CPU Whisper scales with utterance
// length, so a millisecond ceiling that passes a 30s Part 1 answer fails every
// two-minute Part 2 answer for reasons that have nothing to do with regression.
//
// # Re-measured against the real sidecar (faster-whisper "small", int8, CPU)
//
// 12 samples of real spoken English swept across the lengths the exam actually
// produces — see perf/reports/*-real-whisper-measurement.json:
//
//	 15s clip -> 7.0-7.2s   ratio 0.466 - 0.480
//	 30s clip -> 11.5-11.9s ratio 0.382 - 0.396
//	 45s clip -> 17.9-19.8s ratio 0.397 - 0.440
//	 68s clip -> 23.4-23.9s ratio 0.344 - 0.351
//
//	 min 0.344   med 0.397   p95 0.472   max 0.480
//
// The ratio is NOT constant: it is worst on SHORT utterances, because the
// model's fixed per-call overhead is amortised over less audio. That inverts
// the intuition the old figure was built on — 0.5 was derived from a single 35s
// clip at ~0.33 and looked like 50% headroom, when in fact a 15s Part 1 answer
// sits at 0.48 and would breach on any ordinary jitter. Raised to 0.6, roughly
// 25% above the measured p95: enough to catch a real regression (a model swap,
// CPU contention) without firing on noise.
var (
	budgetTranscriptionRatio = sloBudget{label: "transcription_ratio", limit: 0.6}

	// Measured end to end against the real provider (AgentRouter, claude-opus-4-8)
	// with the real sidecar, 8 sessions on a 68s Part 2 answer:
	//
	//	 min 28,029   med 28,388   p95 28,728   max 28,728
	//
	// The old 30,000 sat 4% above the measured p95 — passing, but by so little
	// that ordinary provider jitter would have flipped it. One earlier run
	// measured 30,197, i.e. already breaching. Transcription alone accounts for
	// ~22.3s of it, so the budget is really "STT plus the first agent"; 45,000
	// leaves the first agent a realistic ~22s against a provider whose latency
	// is documented from 2.5s to past 110s.
	budgetFirstCriterion = sloBudget{label: "time_to_first_criterion_ms", limit: 45000}

	// Unchanged, and now confirmed rather than assumed. This metric is observed
	// at the first TTS chunk written to the socket, which the same 8 sessions
	// measured at:
	//
	//	 min 38,050   med 43,578   p95 60,715
	//
	// 90,000 leaves ~48% headroom over the measured p95 — enough to absorb the
	// provider's slow tail without the budget becoming decorative.
	budgetE2E = sloBudget{label: "e2e_latency_ms", limit: 90000}
)

// pcmBytesPerMillisecond is derived from the audio format this service actually
// declares, rather than pasted as a magic number: stt.go sends
// "audio/pcm;rate=16000" and the sidecar decodes it as int16 mono
// (services/speech/app/main.py). Writing it as the product means a reader can
// check it against that header, and bumping the sample rate updates the ratio
// SLO instead of quietly invalidating it.
const (
	pcmSampleRate     = 16000 // Hz
	pcmBytesPerSample = 2     // int16, little endian
	pcmChannels       = 1     // mono

	pcmBytesPerMillisecond = pcmSampleRate * pcmBytesPerSample * pcmChannels / 1000
)

// pcmDurationMs returns the wall-clock duration of n bytes of the raw PCM this
// service sends to the speech sidecar.
//
// Returns 0 for a non-positive count. Callers divide by this, and a ratio of
// +Inf poisons a Prometheus histogram's _sum for the lifetime of the process --
// there is no way to un-observe it, so the only recovery is a restart.
func pcmDurationMs(n int) int64 {
	if n <= 0 {
		return 0
	}
	return int64(n) / pcmBytesPerMillisecond
}

// checkSLO records a breach of one budget: it increments the labelled counter
// and logs at WARN with the session and correlation ids, per GOA-032's
// acceptance criteria. It reports whether a breach occurred.
//
// WARN and not ERROR: a breach here is a known, measured property of running
// Whisper on CPU next to a variable-latency LLM gateway, not an operational
// failure. Logging it at ERROR trains the team to ignore ERROR, which costs
// more than the signal is worth.
func (c *Client) checkSLO(b sloBudget, observed float64) bool {
	if observed <= b.limit {
		return false
	}
	sloViolationsMetric.WithLabelValues(b.label).Inc()
	log.Warn().
		Str("session_id", c.id).
		Str("user_id", c.userID).
		Str("correlation_id", c.correlationID).
		Str("budget", b.label).
		Float64("observed", observed).
		Float64("limit", b.limit).
		Msg("SLO breach: speaking latency budget exceeded")
	return true
}
