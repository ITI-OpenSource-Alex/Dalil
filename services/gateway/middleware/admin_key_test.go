package middleware

import (
	"net/http/httptest"
	"testing"

	"github.com/gofiber/fiber/v2"
)

func TestAdminKey(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		expected   string
		provided   string
		wantStatus int
	}{
		{
			name:       "missing header is unauthorized",
			expected:   "configured-admin-key",
			wantStatus: fiber.StatusUnauthorized,
		},
		{
			name:       "wrong header is unauthorized",
			expected:   "configured-admin-key",
			provided:   "wrong-admin-key",
			wantStatus: fiber.StatusUnauthorized,
		},
		{
			name:       "correct header is accepted",
			expected:   "configured-admin-key",
			provided:   "configured-admin-key",
			wantStatus: fiber.StatusOK,
		},
		{
			name:       "unset configured secret fails closed",
			expected:   "",
			provided:   "any-value",
			wantStatus: fiber.StatusUnauthorized,
		},
		{
			name:       "empty configured and provided values fail closed",
			expected:   "",
			provided:   "",
			wantStatus: fiber.StatusUnauthorized,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			app := fiber.New()
			admin := app.Group("/admin", AdminKey(tc.expected))
			admin.Get("/costs", func(c *fiber.Ctx) error {
				return c.SendStatus(fiber.StatusOK)
			})

			req := httptest.NewRequest(fiber.MethodGet, "/admin/costs", nil)
			if tc.provided != "" {
				req.Header.Set("X-Admin-Key", tc.provided)
			}

			resp, err := app.Test(req)
			if err != nil {
				t.Fatalf("admin request returned error: %v", err)
			}
			if resp.StatusCode != tc.wantStatus {
				t.Fatalf("expected status %d, got %d", tc.wantStatus, resp.StatusCode)
			}
		})
	}
}
