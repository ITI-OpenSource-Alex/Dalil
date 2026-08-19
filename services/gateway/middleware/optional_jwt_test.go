package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/golang-jwt/jwt/v5"
)

// newOptionalJWTTestApp mounts OptionalJWT in front of a handler that reports
// whether an identity was resolved, so each case can assert both halves of the
// contract: the request is always allowed through, and the locals are populated
// only when the token was genuinely valid.
//
// Deliberately no Redis client: OptionalJWT takes none, which is itself part of
// what makes /auth/logout survivable when the cache is down.
func newOptionalJWTTestApp() *fiber.App {
	app := fiber.New()
	app.Use(OptionalJWT(testJWTSecret))
	app.Post("/logout", func(c *fiber.Ctx) error {
		userID, _ := c.Locals(ContextKeyUserID).(string)
		if userID == "" {
			return c.SendString("anonymous")
		}
		return c.SendString(userID)
	})
	return app
}

// The regression this file exists for: /auth/logout used to sit behind the
// mandatory JWT middleware, so any token the gateway could not validate
// produced a 401 before AuthHandler.Logout ran. The handler is what clears the
// auth cookies -- so the one situation in which a user most needs to log out
// (a session that has gone bad) was the one situation in which logging out was
// impossible. The button appeared to do nothing, because the browser kept its
// access_token and Next.js middleware bounced /login straight back to /chat.
func TestOptionalJWTAlwaysReachesTheHandler(t *testing.T) {
	tests := []struct {
		name          string
		authorization string
		cookie        string
	}{
		{name: "no credentials at all"},
		{
			name:          "expired token",
			authorization: "Bearer " + signTestAccessToken(t, testJWTSecret, -time.Hour, jwt.SigningMethodHS256),
		},
		{
			name:          "token signed with the wrong secret",
			authorization: "Bearer " + signTestAccessToken(t, "wrong-secret", time.Hour, jwt.SigningMethodHS256),
		},
		{
			name:          "malformed bearer header",
			authorization: "Bearer",
		},
		{
			name:          "garbage cookie",
			cookie:        "not-a-jwt",
		},
		{
			name:   "expired cookie",
			cookie: signTestAccessToken(t, testJWTSecret, -time.Hour, jwt.SigningMethodHS256),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			app := newOptionalJWTTestApp()
			req := httptest.NewRequest(fiber.MethodPost, "/logout", nil)
			if tt.authorization != "" {
				req.Header.Set(fiber.HeaderAuthorization, tt.authorization)
			}
			if tt.cookie != "" {
				req.AddCookie(&http.Cookie{Name: "access_token", Value: tt.cookie})
			}

			resp, err := app.Test(req)
			if err != nil {
				t.Fatalf("request failed: %v", err)
			}
			defer resp.Body.Close()

			if resp.StatusCode != fiber.StatusOK {
				t.Fatalf(
					"expected the handler to be reached (200), got %d -- logout must not require a valid session",
					resp.StatusCode,
				)
			}
		})
	}
}

func TestOptionalJWTResolvesIdentityForAValidToken(t *testing.T) {
	// The other half: when the token *is* good, the handler still learns who is
	// calling, so logout can revoke that user's refresh token and blacklist the
	// jti rather than only clearing cookies.
	app := newOptionalJWTTestApp()
	req := httptest.NewRequest(fiber.MethodPost, "/logout", nil)
	req.Header.Set(
		fiber.HeaderAuthorization,
		"Bearer "+signTestAccessToken(t, testJWTSecret, time.Hour, jwt.SigningMethodHS256),
	)

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != fiber.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	body := make([]byte, 64)
	n, _ := resp.Body.Read(body)
	got := string(body[:n])
	if got != "00000000-0000-0000-0000-000000000001" {
		t.Fatalf("expected the subject in ContextKeyUserID, got %q", got)
	}
}

func TestOptionalJWTLeavesIdentityUnsetForABadToken(t *testing.T) {
	app := newOptionalJWTTestApp()
	req := httptest.NewRequest(fiber.MethodPost, "/logout", nil)
	req.Header.Set(
		fiber.HeaderAuthorization,
		"Bearer "+signTestAccessToken(t, "wrong-secret", time.Hour, jwt.SigningMethodHS256),
	)

	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()

	body := make([]byte, 64)
	n, _ := resp.Body.Read(body)
	// An unverifiable token must never be allowed to assert an identity -- it
	// is passed through, not trusted.
	if got := string(body[:n]); got != "anonymous" {
		t.Fatalf("expected no identity from an unverifiable token, got %q", got)
	}
}
