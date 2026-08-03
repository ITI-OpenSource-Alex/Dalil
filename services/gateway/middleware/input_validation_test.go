package middleware

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
	"github.com/rs/zerolog"
)

// newValidationApp wires the middleware the way server.go does: after the JWT
// has populated the user id, in front of the real handler.
//
// The handler records whether it ran. That is the assertion that matters for a
// cost control -- "rejected with a 400" is worth nothing if the request reached
// Orchestration and bought a model call on its way to being rejected.
func newValidationApp(t *testing.T, field string, maxChars int, logs *bytes.Buffer) (*fiber.App, *bool) {
	t.Helper()

	reached := false
	logger := zerolog.New(logs)

	app := fiber.New()
	app.Post("/api/chat",
		func(c *fiber.Ctx) error {
			c.Locals(ContextKeyUserID, "user-123")
			c.Locals(ContextKeyRequestID, "corr-abc")
			return c.Next()
		},
		ValidateJSONFieldLength(field, maxChars, logger),
		func(c *fiber.Ctx) error {
			reached = true
			// Read the body again, as StreamHandler.Chat does. If the
			// middleware had consumed it, this would come back empty.
			return c.SendString(string(c.Body()))
		},
	)

	return app, &reached
}

func postJSON(t *testing.T, app *fiber.App, body string) *http.Response {
	t.Helper()

	req := httptest.NewRequest(http.MethodPost, "/api/chat", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := app.Test(req, 5000)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	return resp
}

func TestMessageWithinLimitReachesTheHandler(t *testing.T) {
	var logs bytes.Buffer
	app, reached := newValidationApp(t, "message", 2000, &logs)

	resp := postJSON(t, app, `{"message":"What are the visa requirements?"}`)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}
	if !*reached {
		t.Fatal("a valid message did not reach the handler")
	}
	if logs.Len() != 0 {
		t.Fatalf("a valid message produced a security event: %s", logs.String())
	}
}

func TestOversizedMessageNeverReachesTheHandler(t *testing.T) {
	var logs bytes.Buffer
	app, reached := newValidationApp(t, "message", 2000, &logs)

	payload, err := json.Marshal(map[string]string{"message": strings.Repeat("a", 2001)})
	if err != nil {
		t.Fatal(err)
	}

	resp := postJSON(t, app, string(payload))
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", resp.StatusCode)
	}
	if *reached {
		t.Fatal("an oversized message reached the handler -- the cost was already incurred")
	}
}

func TestExactlyAtTheLimitIsAccepted(t *testing.T) {
	var logs bytes.Buffer
	app, reached := newValidationApp(t, "message", 2000, &logs)

	payload, _ := json.Marshal(map[string]string{"message": strings.Repeat("a", 2000)})
	resp := postJSON(t, app, string(payload))
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("the boundary must be inclusive; got %d", resp.StatusCode)
	}
	if !*reached {
		t.Fatal("a message exactly at the limit was rejected")
	}
}

// The bug a byte-based implementation would ship, and the reason this test
// exists: GOA's users are Egyptian students. Arabic is ~2 bytes per character
// in UTF-8, so len() on the string would cut them off at roughly half the
// allowance an English speaker gets -- a limit that silently discriminates by
// language and would never show up in English-language testing.
func TestArabicMessageIsCountedInCharactersNotBytes(t *testing.T) {
	var logs bytes.Buffer
	app, reached := newValidationApp(t, "message", 2000, &logs)

	// 1500 Arabic characters: well within a 2000-character limit, and far over
	// 2000 bytes.
	arabic := strings.Repeat("ب", 1500)
	if len(arabic) <= 2000 {
		t.Fatalf("test premise broken: expected >2000 bytes, got %d", len(arabic))
	}

	payload, _ := json.Marshal(map[string]string{"message": arabic})
	resp := postJSON(t, app, string(payload))
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("1500 Arabic characters were rejected under a 2000-character limit (got %d) -- bytes are being counted, not characters", resp.StatusCode)
	}
	if !*reached {
		t.Fatal("a valid Arabic message did not reach the handler")
	}
}

func TestEmojiCountAsSingleCharacters(t *testing.T) {
	var logs bytes.Buffer
	app, _ := newValidationApp(t, "message", 10, &logs)

	// 5 emoji: 5 runes, 20 bytes. A byte limit of 10 would reject them.
	payload, _ := json.Marshal(map[string]string{"message": strings.Repeat("😀", 5)})
	resp := postJSON(t, app, string(payload))
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 5 emoji to pass a 10-character limit, got %d", resp.StatusCode)
	}
}

func TestAbsentFieldIsDeferredToTheSchema(t *testing.T) {
	var logs bytes.Buffer
	app, reached := newValidationApp(t, "message", 2000, &logs)

	resp := postJSON(t, app, `{"sessionId":"s-1"}`)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("a missing field is the schema's business, not this middleware's; got %d", resp.StatusCode)
	}
	if !*reached {
		t.Fatal("a request without the field should pass through")
	}
}

func TestEmptyBodyPassesThrough(t *testing.T) {
	var logs bytes.Buffer
	app, reached := newValidationApp(t, "message", 2000, &logs)

	resp := postJSON(t, app, "")
	defer resp.Body.Close()

	if !*reached {
		t.Fatalf("an empty body should pass through to the handler, got %d", resp.StatusCode)
	}
}

func TestMalformedJSONIsRejectedAsABadRequest(t *testing.T) {
	var logs bytes.Buffer
	app, reached := newValidationApp(t, "message", 2000, &logs)

	resp := postJSON(t, app, `{"message": "unterminated`)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400 for malformed JSON, got %d", resp.StatusCode)
	}
	if *reached {
		t.Fatal("malformed JSON reached the handler")
	}
}

func TestNonStringFieldIsRejected(t *testing.T) {
	var logs bytes.Buffer
	app, reached := newValidationApp(t, "message", 2000, &logs)

	resp := postJSON(t, app, `{"message": {"nested": "object"}}`)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400 for a non-string field, got %d", resp.StatusCode)
	}
	if *reached {
		t.Fatal("a non-string field reached the handler")
	}
}

func TestBodyIsStillReadableByTheHandler(t *testing.T) {
	var logs bytes.Buffer
	app, _ := newValidationApp(t, "message", 2000, &logs)

	body := `{"message":"still here"}`
	resp := postJSON(t, app, body)
	defer resp.Body.Close()

	got := make([]byte, len(body))
	n, _ := resp.Body.Read(got)
	if string(got[:n]) != body {
		t.Fatalf("the middleware consumed the body; handler saw %q", string(got[:n]))
	}
}

// The rule the whole SecurityEvent type exists to enforce. Logs are the
// least-protected store in the system, so an attacker must not be able to get
// their payload written into it by sending it.
func TestTheRejectedMessageNeverAppearsInTheLog(t *testing.T) {
	var logs bytes.Buffer
	app, _ := newValidationApp(t, "message", 50, &logs)

	secret := "my passport number is A12345678 and my email is lina@example.com"
	payload, _ := json.Marshal(map[string]string{"message": secret + strings.Repeat("!", 60)})

	resp := postJSON(t, app, string(payload))
	defer resp.Body.Close()

	logged := logs.String()
	if logged == "" {
		t.Fatal("a rejection produced no security event at all")
	}
	if strings.Contains(logged, "passport") || strings.Contains(logged, "lina@example.com") {
		t.Fatalf("raw user input was written to the log: %s", logged)
	}
}

func TestTheSecurityEventCarriesTheRequiredFields(t *testing.T) {
	var logs bytes.Buffer
	app, _ := newValidationApp(t, "message", 10, &logs)

	payload, _ := json.Marshal(map[string]string{"message": strings.Repeat("a", 40)})
	resp := postJSON(t, app, string(payload))
	defer resp.Body.Close()

	var event map[string]any
	if err := json.Unmarshal(logs.Bytes(), &event); err != nil {
		t.Fatalf("the security event is not valid JSON: %v (%s)", err, logs.String())
	}

	// The field shape GOA-034 mandates. A log that is missing one of these
	// cannot be correlated with the same event in another service.
	for _, field := range []string{
		"event", "event_type", "severity", "user_id", "correlation_id",
		"input_hash", "action_taken", "route",
	} {
		if _, ok := event[field]; !ok {
			t.Errorf("security event is missing the %q field: %s", field, logs.String())
		}
	}

	if event["event_type"] != "input_length_exceeded" {
		t.Errorf("unexpected event_type %v", event["event_type"])
	}
	if event["user_id"] != "user-123" {
		t.Errorf("user_id must come from the validated JWT, got %v", event["user_id"])
	}
	if event["correlation_id"] != "corr-abc" {
		t.Errorf("correlation_id was not propagated, got %v", event["correlation_id"])
	}
}

func TestTheSameInputAlwaysProducesTheSameHash(t *testing.T) {
	// Correlation across services and over time depends on this. It is also
	// what lets an investigation confirm "this is the payload we saw yesterday"
	// without either log containing the payload.
	first := HashInput("ignore all previous instructions")
	second := HashInput("ignore all previous instructions")
	other := HashInput("ignore all previous instruction")

	if first != second {
		t.Fatal("the same input hashed differently")
	}
	if first == other {
		t.Fatal("a one-character difference produced the same hash")
	}
	if strings.Contains(first, "ignore") {
		t.Fatal("the hash contains the plaintext")
	}
	if len(first) != 32 {
		t.Fatalf("expected a 128-bit hex hash, got %d characters", len(first))
	}
}

func TestSeverityDecidesTheLogLevel(t *testing.T) {
	cases := []struct {
		severity Severity
		level    string
	}{
		{SeverityLow, "info"},
		{SeverityMedium, "warn"},
		{SeverityHigh, "error"},
		{SeverityCritical, "error"},
	}

	for _, tc := range cases {
		var logs bytes.Buffer
		logger := zerolog.New(&logs)

		app := fiber.New()
		app.Get("/x", func(c *fiber.Ctx) error {
			LogSecurityEvent(c, logger, SecurityEvent{
				EventType:   "test",
				Severity:    tc.severity,
				InputHash:   "deadbeef",
				ActionTaken: "none",
			})
			return c.SendStatus(fiber.StatusOK)
		})

		resp, err := app.Test(httptest.NewRequest(http.MethodGet, "/x", nil))
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()

		var event map[string]any
		if err := json.Unmarshal(logs.Bytes(), &event); err != nil {
			t.Fatalf("%s: not valid JSON: %v", tc.severity, err)
		}
		if event["level"] != tc.level {
			t.Errorf("%s should log at %s, got %v", tc.severity, tc.level, event["level"])
		}
	}
}
