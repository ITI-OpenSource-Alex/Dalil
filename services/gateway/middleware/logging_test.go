package middleware_test

import (
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/rs/zerolog"
)

// BUG-031: fasthttp reuses its request buffer, and Fiber's c.Method()/c.Path()
// return zero-copy strings over it. Prometheus retains label values for the
// process lifetime, so uncopied labels mutated after the request finished: a POST
// to /auth/login surfaced as method "GETT" and the mutated series then collided
// with the original, making /metrics itself return 500 -- the gateway became
// unscrapeable entirely.
//
// Gathering the registry is the assertion that matters. It is what Prometheus
// does on scrape, and it is what returned the error; a test that only counted
// requests would still have passed while the endpoint was broken.
func TestMetricsStayGatherableAcrossManyRequests(t *testing.T) {
	metrics, err := observability.NewMetrics()
	if err != nil {
		t.Fatalf("NewMetrics: %v", err)
	}

	app := fiber.New()
	app.Use(middleware.RequestLogger(zerolog.Nop(), metrics))
	app.Post("/auth/login", func(c *fiber.Ctx) error { return c.SendStatus(fiber.StatusOK) })
	app.Get("/health", func(c *fiber.Ctx) error { return c.SendStatus(fiber.StatusOK) })

	// Mix matched routes with unmatched ones: a 404 takes the c.Path() fallback,
	// which is the other buffer-backed string on this path.
	for i := 0; i < 40; i++ {
		for _, r := range []struct{ method, path string }{
			{fiber.MethodPost, "/auth/login"},
			{fiber.MethodGet, "/health"},
			{fiber.MethodGet, "/api/chat"},
			{fiber.MethodPost, "/api/opportunities/query"},
		} {
			resp, err := app.Test(httptest.NewRequest(r.method, r.path, nil))
			if err != nil {
				t.Fatalf("request %s %s: %v", r.method, r.path, err)
			}
			resp.Body.Close()
		}
	}

	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("registry became ungatherable, /metrics would 500: %v", err)
	}

	for _, fam := range families {
		if fam.GetName() != "goa_gateway_requests_total" {
			continue
		}
		for _, m := range fam.GetMetric() {
			for _, label := range m.GetLabel() {
				if label.GetName() != "method" {
					continue
				}
				switch label.GetValue() {
				case fiber.MethodGet, fiber.MethodPost, fiber.MethodPut,
					fiber.MethodPatch, fiber.MethodDelete, fiber.MethodHead,
					fiber.MethodOptions:
				default:
					t.Errorf("corrupted method label %q -- the label string was not copied "+
						"before Prometheus retained it", label.GetValue())
				}
			}
			for _, label := range m.GetLabel() {
				if label.GetName() == "route" && strings.ContainsAny(label.GetValue(), "\x00") {
					t.Errorf("corrupted route label %q", label.GetValue())
				}
			}
		}
	}
}
