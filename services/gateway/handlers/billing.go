package handlers

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

// BillingHandler exposes the subscription upgrade flow and proxies it to the
// User service, which owns both the billing logic and the subscriptionTier
// column (GOA-039).
//
// There is no payment-provider webhook. This project uses a self-contained
// demo payment, so the outcome is settled synchronously by an authenticated
// call from the user's own browser rather than by an external callback. That
// removes the one route that would have had to be public and unauthenticated;
// every billing route below sits inside the /api group and carries JWT auth,
// the request rate limiter and a correlation id like everything else.
type BillingHandler struct {
	httpClient     *http.Client
	userServiceURL string
	internalAPIKey string
	// Origins a checkout may return the browser to. Reuses the Gateway's
	// existing CORS allow-list rather than adding a second, drift-prone list
	// of "our own front ends".
	allowedOrigins []string
}

func NewBillingHandler(
	httpClient *http.Client,
	userServiceURL string,
	internalAPIKey string,
	allowedOrigins string,
) *BillingHandler {
	origins := make([]string, 0)
	for _, origin := range strings.Split(allowedOrigins, ",") {
		trimmed := strings.TrimRight(strings.TrimSpace(origin), "/")
		if trimmed != "" {
			origins = append(origins, trimmed)
		}
	}

	return &BillingHandler{
		httpClient:     httpClient,
		userServiceURL: strings.TrimRight(userServiceURL, "/"),
		internalAPIKey: internalAPIKey,
		allowedOrigins: origins,
	}
}

type createCheckoutRequest struct {
	SuccessURL string `json:"successUrl"`
	CancelURL  string `json:"cancelUrl"`
}

type confirmPaymentRequest struct {
	Token      string `json:"token"`
	CardNumber string `json:"cardNumber"`
}

// proxyBilling forwards an authenticated billing call to the User service.
//
// Shared by every billing route because they differ only in path and payload:
// same identity handling (JWT-derived, sent as X-User-Id), same internal key,
// and the same status/body pass-through so an upstream 409 or 400 reaches the
// browser as itself rather than as a flattened 502.
func (h *BillingHandler) proxyBilling(
	c *fiber.Ctx,
	userID string,
	path string,
	payload any,
) (*http.Response, []byte, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, nil, fiber.NewError(fiber.StatusInternalServerError, "internal request error")
	}

	req, err := http.NewRequestWithContext(
		c.UserContext(),
		http.MethodPost,
		h.userServiceURL+path,
		bytes.NewReader(body),
	)
	if err != nil {
		return nil, nil, fiber.NewError(fiber.StatusInternalServerError, "internal request error")
	}
	req.Header.Set("X-Internal-Api-Key", h.internalAPIKey)
	req.Header.Set("X-User-Id", userID)
	req.Header.Set(fiber.HeaderContentType, "application/json")
	if requestID, _ := c.Locals(middleware.ContextKeyRequestID).(string); requestID != "" {
		req.Header.Set(middleware.HeaderCorrelationID, requestID)
	}

	resp, err := h.httpClient.Do(req)
	if err != nil {
		return nil, nil, fiber.NewError(fiber.StatusBadGateway, "failed to contact user service")
	}
	defer resp.Body.Close()

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, nil, err
	}
	return resp, responseBody, nil
}

// relayUpstream sends an upstream response back to the browser unchanged.
func relayUpstream(c *fiber.Ctx, resp *http.Response, body []byte) error {
	c.Status(resp.StatusCode)
	c.Set(fiber.HeaderContentType, resp.Header.Get(fiber.HeaderContentType))
	return c.Send(body)
}

// CreateCheckout handles POST /api/billing/create-checkout.
//
// The user id comes from the validated JWT and is passed downstream as
// X-User-Id; the request body carries no identity, no price and no tier, so
// none of them can be chosen by the caller.
//
// The User service mints an opaque single-use token and this handler turns it
// into the checkout URL, because the Gateway is the layer that knows which
// origins belong to us.
func (h *BillingHandler) CreateCheckout(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	var payload createCheckoutRequest
	// An empty body is fine and common -- the defaults below cover it. Only a
	// malformed one is an error.
	if len(c.Body()) > 0 {
		if err := json.Unmarshal(c.Body(), &payload); err != nil {
			return fiber.NewError(fiber.StatusBadRequest, "invalid request body")
		}
	}

	successURL, err := h.resolveReturnURL(payload.SuccessURL, "/billing/success")
	if err != nil {
		return err
	}
	cancelURL, err := h.resolveReturnURL(payload.CancelURL, "/pricing?checkout=cancelled")
	if err != nil {
		return err
	}

	resp, body, err := h.proxyBilling(c, userID, "/billing/checkout", map[string]string{
		"successUrl": successURL,
		"cancelUrl":  cancelURL,
	})
	if err != nil {
		return err
	}

	// Anything other than a created session is relayed as-is: 409 for an
	// account that already has the plan, 503 when billing is switched off.
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return relayUpstream(c, resp, body)
	}

	var created struct {
		Token string `json:"token"`
	}
	if err := json.Unmarshal(body, &created); err != nil || created.Token == "" {
		return fiber.NewError(fiber.StatusBadGateway, "billing returned an unexpected response")
	}

	// Built here, from an origin already proven to be ours, so the browser is
	// never sent anywhere this Gateway has not vouched for.
	origin, err := originOf(successURL)
	if err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "internal request error")
	}

	return c.JSON(fiber.Map{
		"url": origin + "/billing/demo-checkout?session=" + url.QueryEscape(created.Token),
	})
}

// ConfirmPayment handles POST /api/billing/demo/confirm.
//
// The demo checkout page calls this with the token it was handed and whatever
// was typed into the card field. The Gateway adds the authenticated identity;
// the User service decides the outcome and, on success, is the only thing that
// touches the subscription tier.
func (h *BillingHandler) ConfirmPayment(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	var payload confirmPaymentRequest
	if err := json.Unmarshal(c.Body(), &payload); err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "invalid request body")
	}

	resp, body, err := h.proxyBilling(c, userID, "/billing/demo/confirm", map[string]string{
		"token":      payload.Token,
		"cardNumber": payload.CardNumber,
	})
	if err != nil {
		return err
	}
	return relayUpstream(c, resp, body)
}

// CancelSubscription handles POST /api/billing/cancel.
//
// The demo equivalent of a hosted billing portal's cancel button. No payload
// at all: which subscription is being cancelled follows from the JWT.
func (h *BillingHandler) CancelSubscription(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}

	resp, body, err := h.proxyBilling(c, userID, "/billing/cancel", map[string]string{})
	if err != nil {
		return err
	}
	return relayUpstream(c, resp, body)
}

func originOf(raw string) (string, error) {
	parsed, err := url.Parse(raw)
	if err != nil {
		return "", err
	}
	return parsed.Scheme + "://" + parsed.Host, nil
}

// resolveReturnURL validates a client-supplied return URL, or builds the
// server-side default when none was sent.
//
// The browser is redirected to whatever these say after a checkout that began
// on our domain with our branding, so an unvalidated value is a working
// phishing primitive rather than a theoretical one -- and the checkout URL
// itself is derived from the success URL's origin, so a foreign value would
// also decide where the payment form is served from. Only origins already
// trusted enough to make credentialed cross-origin calls to this Gateway are
// accepted, and anything else is rejected rather than quietly replaced (a
// silent substitution would hide a misconfigured front end).
func (h *BillingHandler) resolveReturnURL(candidate string, defaultPath string) (string, error) {
	if candidate == "" {
		if len(h.allowedOrigins) == 0 {
			return "", fiber.NewError(
				fiber.StatusInternalServerError,
				"no allowed origin is configured for billing return URLs",
			)
		}
		return h.allowedOrigins[0] + defaultPath, nil
	}

	parsed, err := url.Parse(candidate)
	if err != nil || !parsed.IsAbs() || parsed.Host == "" {
		return "", fiber.NewError(fiber.StatusBadRequest, "invalid return URL")
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return "", fiber.NewError(fiber.StatusBadRequest, "invalid return URL")
	}
	// Userinfo is what turns https://app.example@evil.test/ into a URL that
	// reads as ours and resolves as theirs.
	if parsed.User != nil {
		return "", fiber.NewError(fiber.StatusBadRequest, "invalid return URL")
	}

	origin := parsed.Scheme + "://" + parsed.Host
	for _, allowed := range h.allowedOrigins {
		if strings.EqualFold(origin, allowed) {
			return candidate, nil
		}
	}
	return "", fiber.NewError(fiber.StatusBadRequest, "return URL is not an allowed origin")
}
