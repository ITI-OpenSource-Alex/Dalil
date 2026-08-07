package middleware

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
)

// TestExamStartRateLimiterBlocksFourthStart is the DoD unit case: three sessions
// in an hour are allowed, the fourth is not.
func TestExamStartRateLimiterBlocksFourthStart(t *testing.T) {
	app := newExamStartTestApp(newFakeRateLimitStore(), 3)

	for i := range 3 {
		resp := performExamStartRequest(t, app)
		if resp.StatusCode != fiber.StatusOK {
			t.Fatalf("exam start %d expected 200, got %d", i+1, resp.StatusCode)
		}
	}

	resp := performExamStartRequest(t, app)
	if resp.StatusCode != fiber.StatusTooManyRequests {
		t.Fatalf("expected the 4th exam start to return 429, got %d", resp.StatusCode)
	}
	if retryAfter := resp.Header.Get(fiber.HeaderRetryAfter); retryAfter == "" {
		t.Fatal("expected Retry-After on the rejected exam start")
	}
}

func TestExamStartRateLimiterUsesTheTicketKeyFormat(t *testing.T) {
	store := newFakeRateLimitStore()
	app := newExamStartTestApp(store, 3)

	if resp := performExamStartRequest(t, app); resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	keys := keysOf(store.counts)
	if len(keys) != 1 {
		t.Fatalf("expected exactly one counter, got %v", keys)
	}
	// The hour suffix is not compared literally: the window can roll over between
	// the request and this assertion, and that is not a defect.
	if !strings.HasPrefix(keys[0], "exam_start:user-1:") {
		t.Fatalf("expected an exam_start:{userId}:{hour} key, got %q", keys[0])
	}
	if _, err := time.Parse("2006-01-02T15", strings.TrimPrefix(keys[0], "exam_start:user-1:")); err != nil {
		t.Fatalf("expected a calendar-hour suffix in %q: %v", keys[0], err)
	}
	if ttl := store.ttls[keys[0]]; ttl != time.Hour {
		t.Fatalf("expected a one hour window, got %s", ttl)
	}
}

// A different candidate must have their own counter, or one heavy user would
// throttle everybody.
func TestExamStartRateLimiterIsPerUser(t *testing.T) {
	store := newFakeRateLimitStore()
	first := newExamStartTestAppForUser(store, 3, "user-1")
	second := newExamStartTestAppForUser(store, 3, "user-2")

	for range 3 {
		if resp := performExamStartRequest(t, first); resp.StatusCode != fiber.StatusOK {
			t.Fatalf("expected user-1 to be allowed, got %d", resp.StatusCode)
		}
	}
	if resp := performExamStartRequest(t, first); resp.StatusCode != fiber.StatusTooManyRequests {
		t.Fatalf("expected user-1 to be limited, got %d", resp.StatusCode)
	}
	if resp := performExamStartRequest(t, second); resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected user-2 to be unaffected, got %d", resp.StatusCode)
	}
}

func TestExamStartRateLimiterRequiresAnAuthenticatedUser(t *testing.T) {
	app := fiber.New()
	app.Use(ExamStartRateLimiter(newFakeRateLimitStore(), 3))
	app.Post("/api/exam/sessions", func(c *fiber.Ctx) error {
		return c.SendStatus(fiber.StatusOK)
	})

	resp := performExamStartRequest(t, app)
	if resp.StatusCode != fiber.StatusUnauthorized {
		t.Fatalf("expected 401 without an authenticated user, got %d", resp.StatusCode)
	}
}

func newExamStartTestApp(store RateLimitStore, limit int) *fiber.App {
	return newExamStartTestAppForUser(store, limit, "user-1")
}

func newExamStartTestAppForUser(store RateLimitStore, limit int, userID string) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		c.Locals(ContextKeyUserID, userID)
		return c.Next()
	})
	app.Use(ExamStartRateLimiter(store, limit))
	app.Post("/api/exam/sessions", func(c *fiber.Ctx) error {
		return c.SendStatus(fiber.StatusOK)
	})

	return app
}

func performExamStartRequest(t *testing.T, app *fiber.App) *http.Response {
	t.Helper()
	resp, err := app.Test(httptest.NewRequest(fiber.MethodPost, "/api/exam/sessions", nil), -1)
	if err != nil {
		t.Fatalf("perform exam start request: %v", err)
	}
	t.Cleanup(func() { resp.Body.Close() })
	return resp
}

func keysOf(counts map[string]int64) []string {
	names := make([]string, 0, len(counts))
	for name := range counts {
		names = append(names, name)
	}
	return names
}
