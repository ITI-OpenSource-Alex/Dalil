package middleware

import (
	"crypto/sha256"
	"encoding/hex"

	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog"
)

// Severity ranks a security event. It is a field on the log line, not just a
// log level, because the two answer different questions: the level decides
// whether a human is woken up, the field is what you filter on when reviewing a
// month of events.
type Severity string
const (
	SeverityLow      Severity = "LOW"
	SeverityMedium   Severity = "MEDIUM"
	SeverityHigh     Severity = "HIGH"
	SeverityCritical Severity = "CRITICAL"
)

// SecurityEvent is the GOA-034 log contract: {event_type, severity, user_id,
// correlation_id, input_hash, action_taken}.
//
// Note what is absent: the input itself. Logs are the least-protected store in
// the system -- they stream to aggregators, they are read by anyone with
// dashboard access, and they are not covered by the deletion promise that
// GOA-038's DELETE /api/sessions/memory makes about the database. Logging raw
// input on every suspicious request would build a machine that copies user
// data into that store, triggered by attackers. The hash preserves everything
// an investigation actually needs.
type SecurityEvent struct {
	EventType   string
	Severity    Severity
	InputHash   string
	ActionTaken string
	Extra       map[string]any
}


// HashInput fingerprints untrusted input so it can be correlated but not read.
//
// Truncated to 128 bits: enough that two different payloads will not collide in
// any realistic volume, short enough to read in a terminal. SHA-256 is one-way,
// so the original text cannot be recovered from a log.
func HashInput(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:16])
}


// LogSecurityEvent writes one structured line in the GOA-034 shape.
//
// user_id comes from the validated JWT via Locals, never from the request body:
// an attacker controls the body, so a user_id read from it would let them
// attribute their own attacks to someone else.
func LogSecurityEvent(c *fiber.Ctx, logger zerolog.Logger, event SecurityEvent) {
	userID, _ := c.Locals(ContextKeyUserID).(string)
	if userID == "" {
		userID = AnonymousUserIdentifier
	}
	correlationID, _ := c.Locals(ContextKeyRequestID).(string)

	var entry *zerolog.Event
	switch event.Severity {
	case SeverityCritical, SeverityHigh:
		entry = logger.Error()
	case SeverityMedium:
		entry = logger.Warn()
	default:
		entry = logger.Info()
	}

	entry = entry.
		Str("event", "SECURITY_EVENT").
		Str("event_type", event.EventType).
		Str("severity", string(event.Severity)).
		Str("user_id", userID).
		Str("correlation_id", correlationID).
		Str("input_hash", event.InputHash).
		Str("action_taken", event.ActionTaken).
		Str("route", c.Route().Path)

	for key, value := range event.Extra {
		entry = entry.Interface(key, value)
	}

	entry.Msg("security_event")
}
