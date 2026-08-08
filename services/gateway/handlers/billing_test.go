package handlers

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

const allowedOrigins = "http://localhost:3000,https://app.goa.test"

func billingTestApp(handler *BillingHandler, userID string) *fiber.App {
	app := fiber.New()
	app.Use(func(c *fiber.Ctx) error {
		if userID != "" {
			c.Locals(middleware.ContextKeyUserID, userID)
		}
		return c.Next()
	})
	app.Post("/api/billing/create-checkout", handler.CreateCheckout)
	app.Post("/api/billing/demo/confirm", handler.ConfirmPayment)
	app.Post("/api/billing/cancel", handler.CancelSubscription)
	return app
}

func postJSON(t *testing.T, app *fiber.App, path, body string) *http.Response {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	response, err := app.Test(request)
	if err != nil {
		t.Fatal(err)
	}
	return response
}

// upstream spins a fake User service that records what the Gateway sent it.
type upstreamCapture struct {
	path   string
	userID string
	apiKey string
	body   map[string]any
}

func fakeUserService(t *testing.T, capture *upstreamCapture, status int, response string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capture.path = r.URL.Path
		capture.userID = r.Header.Get("X-User-Id")
		capture.apiKey = r.Header.Get("X-Internal-Api-Key")
		payload, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(payload, &capture.body)

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(response))
	}))
}

func TestCreateCheckoutReturnsAnInAppCheckoutURL(t *testing.T) {
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusCreated, `{"token":"abc123"}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/create-checkout", `{
		"successUrl":"http://localhost:3000/billing/success",
		"cancelUrl":"http://localhost:3000/pricing?checkout=cancelled"
	}`)
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
	if capture.path != "/billing/checkout" {
		t.Fatalf("unexpected upstream path %q", capture.path)
	}
	// Identity comes from the validated token, never from the payload.
	if capture.userID != "user-123" {
		t.Fatalf("expected the JWT user id forwarded, got %q", capture.userID)
	}
	if capture.apiKey != "internal-key" {
		t.Fatalf("expected the internal API key added by the Gateway, got %q", capture.apiKey)
	}

	body, _ := io.ReadAll(response.Body)
	var payload struct {
		URL string `json:"url"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatal(err)
	}
	// Built from an origin already proven to be ours -- the checkout page is
	// served by this product, not by a third party.
	want := "http://localhost:3000/billing/demo-checkout?session=abc123"
	if payload.URL != want {
		t.Fatalf("expected %q, got %q", want, payload.URL)
	}
}

func TestCreateCheckoutDefaultsReturnURLsWhenClientSendsNone(t *testing.T) {
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusCreated, `{"token":"abc123"}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/create-checkout", ``)
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
	if capture.body["successUrl"] != "http://localhost:3000/billing/success" {
		t.Fatalf("unexpected default success URL %q", capture.body["successUrl"])
	}
	if capture.body["cancelUrl"] != "http://localhost:3000/pricing?checkout=cancelled" {
		t.Fatalf("unexpected default cancel URL %q", capture.body["cancelUrl"])
	}
}

// The return URL decides both where the browser is sent afterwards and which
// origin serves the payment form, so an unvalidated value is a working
// phishing primitive rather than a theoretical one.
func TestCreateCheckoutRejectsReturnURLOutsideTheAllowList(t *testing.T) {
	cases := []struct {
		name string
		body string
	}{
		{"foreign origin", `{"successUrl":"https://evil.test/steal","cancelUrl":"http://localhost:3000/pricing"}`},
		{"foreign cancel", `{"successUrl":"http://localhost:3000/billing/success","cancelUrl":"https://evil.test/x"}`},
		{"userinfo smuggling", `{"successUrl":"https://localhost:3000@evil.test/","cancelUrl":"http://localhost:3000/pricing"}`},
		{"javascript scheme", `{"successUrl":"javascript:alert(1)","cancelUrl":"http://localhost:3000/pricing"}`},
		{"protocol relative", `{"successUrl":"//evil.test/x","cancelUrl":"http://localhost:3000/pricing"}`},
		{"port mismatch", `{"successUrl":"http://localhost:3001/billing/success","cancelUrl":"http://localhost:3000/pricing"}`},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			upstream := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
				t.Fatal("upstream must not be called for a rejected return URL")
			}))
			defer upstream.Close()

			handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
			app := billingTestApp(handler, "user-123")

			response := postJSON(t, app, "/api/billing/create-checkout", testCase.body)
			defer response.Body.Close()

			if response.StatusCode != http.StatusBadRequest {
				t.Fatalf("expected 400, got %d", response.StatusCode)
			}
		})
	}
}

func TestCreateCheckoutAcceptsEverySecondaryAllowedOrigin(t *testing.T) {
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusCreated, `{"token":"abc123"}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/create-checkout", `{
		"successUrl":"https://app.goa.test/billing/success",
		"cancelUrl":"https://app.goa.test/pricing"
	}`)
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 for an allow-listed origin, got %d", response.StatusCode)
	}
	body, _ := io.ReadAll(response.Body)
	if !strings.Contains(string(body), "https://app.goa.test/billing/demo-checkout") {
		t.Fatalf("checkout URL should follow the caller's own origin, got %s", body)
	}
}

// There is no field for a tier, a price or a user at any layer -- this pins
// that extra keys are dropped rather than relayed.
func TestCreateCheckoutDropsClientSuppliedTierAndUserFields(t *testing.T) {
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusCreated, `{"token":"abc123"}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/create-checkout", `{
		"successUrl":"http://localhost:3000/billing/success",
		"cancelUrl":"http://localhost:3000/pricing",
		"tier":"paid",
		"userId":"someone-else"
	}`)
	defer response.Body.Close()

	for _, forbidden := range []string{"tier", "userId", "subscriptionTier"} {
		if _, present := capture.body[forbidden]; present {
			t.Fatalf("client-supplied %q reached the User service", forbidden)
		}
	}
	if capture.userID != "user-123" {
		t.Fatalf("identity must come from the JWT, got %q", capture.userID)
	}
}

func TestCreateCheckoutRelaysUpstreamConflict(t *testing.T) {
	// An already-paid account is refused by the User service; the Gateway must
	// relay that rather than flattening it into a 502 or inventing a URL.
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusConflict,
		`{"message":"This account already has Dalil Pro"}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/create-checkout", `{}`)
	defer response.Body.Close()

	if response.StatusCode != http.StatusConflict {
		t.Fatalf("expected the upstream 409 relayed, got %d", response.StatusCode)
	}
	body, _ := io.ReadAll(response.Body)
	if strings.Contains(string(body), "demo-checkout") {
		t.Fatal("a refused checkout must not produce a checkout URL")
	}
}

func TestCreateCheckoutRejectsAnUpstreamResponseWithNoToken(t *testing.T) {
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusCreated, `{}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/create-checkout", `{}`)
	defer response.Body.Close()

	if response.StatusCode != http.StatusBadGateway {
		t.Fatalf("expected 502, got %d", response.StatusCode)
	}
}

func TestConfirmPaymentForwardsTokenAndCardWithJWTIdentity(t *testing.T) {
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusOK,
		`{"status":"succeeded","redirectUrl":"http://localhost:3000/billing/success"}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/demo/confirm",
		`{"token":"abc123","cardNumber":"4242424242424242"}`)
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
	if capture.path != "/billing/demo/confirm" {
		t.Fatalf("unexpected upstream path %q", capture.path)
	}
	if capture.userID != "user-123" {
		t.Fatalf("expected the JWT user id forwarded, got %q", capture.userID)
	}
	if capture.body["token"] != "abc123" || capture.body["cardNumber"] != "4242424242424242" {
		t.Fatalf("payload not forwarded: %#v", capture.body)
	}
}

func TestConfirmPaymentRelaysADeclineAsSuccess(t *testing.T) {
	// A declined card is a normal outcome the page renders, not a transport
	// error -- so it must arrive as a 200 with a status, not as a 4xx.
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusOK,
		`{"status":"declined","message":"Your card has insufficient funds."}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/demo/confirm",
		`{"token":"abc123","cardNumber":"4000000000009995"}`)
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
	body, _ := io.ReadAll(response.Body)
	if !strings.Contains(string(body), "declined") {
		t.Fatalf("expected the decline relayed, got %s", body)
	}
}

func TestConfirmPaymentDropsAClientSuppliedUserId(t *testing.T) {
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusOK, `{"status":"declined","message":"no"}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/demo/confirm",
		`{"token":"abc123","cardNumber":"4242424242424242","userId":"victim"}`)
	defer response.Body.Close()

	if _, present := capture.body["userId"]; present {
		t.Fatal("a client-supplied user id reached the User service")
	}
	if capture.userID != "user-123" {
		t.Fatalf("identity must come from the JWT, got %q", capture.userID)
	}
}

func TestCancelSubscriptionSendsNothingButTheJWTIdentity(t *testing.T) {
	capture := &upstreamCapture{}
	upstream := fakeUserService(t, capture, http.StatusOK, `{"subscriptionTier":"free"}`)
	defer upstream.Close()

	handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
	app := billingTestApp(handler, "user-123")

	response := postJSON(t, app, "/api/billing/cancel", `{"userId":"victim"}`)
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}
	if capture.path != "/billing/cancel" {
		t.Fatalf("unexpected upstream path %q", capture.path)
	}
	// Whose subscription is cancelled follows from the token, so the body is
	// empty by construction and cannot name a victim.
	if len(capture.body) != 0 {
		t.Fatalf("expected an empty payload, got %#v", capture.body)
	}
	if capture.userID != "user-123" {
		t.Fatalf("identity must come from the JWT, got %q", capture.userID)
	}
}

func TestBillingRoutesRejectUnauthenticatedCallers(t *testing.T) {
	for _, path := range []string{
		"/api/billing/create-checkout",
		"/api/billing/demo/confirm",
		"/api/billing/cancel",
	} {
		t.Run(path, func(t *testing.T) {
			upstream := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
				t.Fatal("upstream must not be called without an authenticated user")
			}))
			defer upstream.Close()

			handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
			app := billingTestApp(handler, "")

			response := postJSON(t, app, path, `{"token":"abc","cardNumber":"4242424242424242"}`)
			defer response.Body.Close()

			if response.StatusCode != http.StatusUnauthorized {
				t.Fatalf("expected 401, got %d", response.StatusCode)
			}
		})
	}
}

func TestBillingRelaysUpstreamRefusals(t *testing.T) {
	// A spent token (400) and a plan the account does not have (409) must both
	// reach the browser as themselves so the UI can say what went wrong.
	for _, testCase := range []struct {
		path   string
		status int
		body   string
	}{
		{"/api/billing/demo/confirm", http.StatusBadRequest, `{"message":"This checkout has expired"}`},
		{"/api/billing/cancel", http.StatusConflict, `{"message":"This account is not on a paid plan"}`},
	} {
		t.Run(testCase.path, func(t *testing.T) {
			capture := &upstreamCapture{}
			upstream := fakeUserService(t, capture, testCase.status, testCase.body)
			defer upstream.Close()

			handler := NewBillingHandler(upstream.Client(), upstream.URL, "internal-key", allowedOrigins)
			app := billingTestApp(handler, "user-123")

			response := postJSON(t, app, testCase.path,
				`{"token":"abc","cardNumber":"4242424242424242"}`)
			defer response.Body.Close()

			if response.StatusCode != testCase.status {
				t.Fatalf("expected %d relayed, got %d", testCase.status, response.StatusCode)
			}
		})
	}
}
