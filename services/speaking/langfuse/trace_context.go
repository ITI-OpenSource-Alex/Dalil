package langfuse

import (
	"encoding/hex"
	"strings"
)

// ParseTraceparent validates the W3C carrier used by Orchestration. Invalid or
// absent values deliberately return ok=false so direct Speaking connections
// create their own trace instead of dropping telemetry.
func ParseTraceparent(value string) (traceID string, parentObservationID string, ok bool) {
	parts := strings.Split(strings.ToLower(strings.TrimSpace(value)), "-")
	if len(parts) != 4 || parts[0] != "00" || len(parts[3]) != 2 {
		return "", "", false
	}
	if len(parts[1]) != 32 || len(parts[2]) != 16 {
		return "", "", false
	}
	if _, err := hex.DecodeString(parts[1]); err != nil {
		return "", "", false
	}
	if _, err := hex.DecodeString(parts[2]); err != nil {
		return "", "", false
	}
	if parts[1] == strings.Repeat("0", 32) || parts[2] == strings.Repeat("0", 16) {
		return "", "", false
	}

	return parts[1], parts[2], true
}
