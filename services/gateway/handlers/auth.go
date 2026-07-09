package handlers

import (
	"bytes"
	"encoding/json"
	"net/http"
	"os"
	"strings"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
)

type AuthHandler struct {
	redisClient    *redis.Client
	tokenService   *gatewayauth.TokenService
	metrics        *observability.Metrics
	httpClient     *http.Client
	userServiceURL string
	internalAPIKey string
}

type loginResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int64  `json:"expires_in"`
}

type refreshResponse struct {
	AccessToken string `json:"access_token"`
	TokenType   string `json:"token_type"`
	ExpiresIn   int64  `json:"expires_in"`
}

func NewAuthHandler(
	redisClient *redis.Client,
	tokenService *gatewayauth.TokenService,
	metrics *observability.Metrics,
	httpClient *http.Client,
	userServiceURL string,
	internalAPIKey string,
) *AuthHandler {
	return &AuthHandler{
		redisClient:    redisClient,
		tokenService:   tokenService,
		metrics:        metrics,
		httpClient:     httpClient,
		userServiceURL: strings.TrimRight(userServiceURL, "/"),
		internalAPIKey: internalAPIKey,
	}
}

func (h *AuthHandler) Login(c *fiber.Ctx) error {
	var req struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := c.BodyParser(&req); err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "malformed login request")
	}

	req.Email = strings.TrimSpace(req.Email)
	if req.Email == "" || req.Password == "" {
		return fiber.NewError(fiber.StatusBadRequest, "email and password are required")
	}

	// 1. Delegate credentials validation & token generation to User Service
	payload, _ := json.Marshal(map[string]string{
		"email":      req.Email,
		"password":   req.Password,
		"deviceHint": c.Get("User-Agent"),
	})

	httpReq, _ := http.NewRequestWithContext(c.UserContext(), http.MethodPost, h.userServiceURL+"/internal/auth/login", bytes.NewBuffer(payload))
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("X-Internal-Api-Key", h.internalAPIKey)

	resp, err := h.httpClient.Do(httpReq)
	if err != nil {
		return fiber.NewError(fiber.StatusServiceUnavailable, "auth service unavailable")
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "invalid credentials")
	}
	if resp.StatusCode >= 500 {
		return fiber.NewError(fiber.StatusServiceUnavailable, "auth service unavailable")
	}

	var data struct {
		UserId    string    `json:"userId"`
		Email     string    `json:"email"`
		TokenId   string    `json:"tokenId"`
		RawToken  string    `json:"rawToken"`
		ExpiresAt time.Time `json:"expiresAt"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "invalid response from auth service")
	}

	// 2. Generate Access Token locally
	user := gatewayauth.User{ID: data.UserId, Email: data.Email}
	accessToken, err := h.tokenService.NewAccessToken(user)
	if err != nil {
		return err
	}

	// 3. Write Cookies
	secure := os.Getenv("SECURE_COOKIES") == "true"
	c.Cookie(&fiber.Cookie{
		Name:     "access_token",
		Value:    accessToken,
		HTTPOnly: true,
		Secure:   secure,
		SameSite: "Lax",
		Path:     "/",
		Expires:  time.Now().Add(1 * time.Hour),
	})
	c.Cookie(&fiber.Cookie{
		Name:     "refresh_token",
		Value:    data.TokenId + "." + data.RawToken,
		HTTPOnly: true,
		Secure:   secure,
		SameSite: "Lax",
		Path:     "/auth/refresh",
		Expires:  data.ExpiresAt,
	})

	return c.JSON(loginResponse{
		AccessToken:  accessToken,
		RefreshToken: data.TokenId + "." + data.RawToken,
		TokenType:    "Bearer",
		ExpiresIn:    int64(h.tokenService.AccessTokenTTL().Seconds()),
	})
}

func (h *AuthHandler) Refresh(c *fiber.Ctx) error {
	refreshTokenValue := c.Cookies("refresh_token")
	if refreshTokenValue == "" {
		// Fallback for tests via JSON body
		var req struct {
			RefreshToken string `json:"refresh_token"`
		}
		_ = c.BodyParser(&req)
		refreshTokenValue = strings.TrimSpace(req.RefreshToken)
	}

	if refreshTokenValue == "" {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusBadRequest, "refresh_token is required")
	}

	parts := strings.SplitN(refreshTokenValue, ".", 2)
	if len(parts) != 2 {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "invalid refresh token format")
	}
	tokenID, rawToken := parts[0], parts[1]

	// 1. Delegate rotation & replay detection to User Service
	payload, _ := json.Marshal(map[string]string{
		"tokenId":    tokenID,
		"rawToken":   rawToken,
		"deviceHint": c.Get("User-Agent"),
	})

	httpReq, _ := http.NewRequestWithContext(c.UserContext(), http.MethodPost, h.userServiceURL+"/internal/auth/refresh-tokens", bytes.NewBuffer(payload))
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("X-Internal-Api-Key", h.internalAPIKey)

	resp, err := h.httpClient.Do(httpReq)
	if err != nil {
		return fiber.NewError(fiber.StatusServiceUnavailable, "auth service unavailable")
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusUnauthorized {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "invalid or expired refresh token")
	}
	if resp.StatusCode == http.StatusForbidden {
		h.metrics.RecordAuthFailure()
		// Replay attack detected! We must clear cookies locally and fail.
		h.clearCookies(c)
		return fiber.NewError(fiber.StatusUnauthorized, "token already revoked, session terminated")
	}
	if resp.StatusCode >= 500 {
		return fiber.NewError(fiber.StatusServiceUnavailable, "auth service unavailable")
	}

	var data struct {
		UserId      string    `json:"userId"`
		Email       string    `json:"email"`
		NewTokenId  string    `json:"newTokenId"`
		NewRawToken string    `json:"newRawToken"`
		ExpiresAt   time.Time `json:"expiresAt"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return fiber.NewError(fiber.StatusInternalServerError, "invalid response from auth service")
	}

	// 2. Issue new Access Token locally
	user := gatewayauth.User{ID: data.UserId, Email: data.Email}
	newAccessToken, err := h.tokenService.NewAccessToken(user)
	if err != nil {
		return err
	}

	// 3. Write Rotated Cookies
	secure := os.Getenv("SECURE_COOKIES") == "true"
	c.Cookie(&fiber.Cookie{
		Name:     "access_token",
		Value:    newAccessToken,
		HTTPOnly: true,
		Secure:   secure,
		SameSite: "Lax",
		Path:     "/",
		Expires:  time.Now().Add(1 * time.Hour),
	})
	c.Cookie(&fiber.Cookie{
		Name:     "refresh_token",
		Value:    data.NewTokenId + "." + data.NewRawToken,
		HTTPOnly: true,
		Secure:   secure,
		SameSite: "Lax",
		Path:     "/auth/refresh",
		Expires:  data.ExpiresAt,
	})

	return c.JSON(refreshResponse{
		AccessToken: newAccessToken,
		TokenType:   "Bearer",
		ExpiresIn:   int64(h.tokenService.AccessTokenTTL().Seconds()),
	})
}

func (h *AuthHandler) Logout(c *fiber.Ctx) error {
	refreshTokenValue := c.Cookies("refresh_token")
	if refreshTokenValue != "" {
		parts := strings.SplitN(refreshTokenValue, ".", 2)
		if len(parts) == 2 {
			payload, _ := json.Marshal(map[string]interface{}{
				"tokenId":   parts[0],
				"revokeAll": false,
			})
			h.fireAndForgetRevoke(c, payload)
		}
	}

	h.blacklistCurrentAccessToken(c)
	h.clearCookies(c)
	return c.SendStatus(fiber.StatusOK)
}

func (h *AuthHandler) LogoutAll(c *fiber.Ctx) error {
	userID, ok := c.Locals(middleware.ContextKeyUserID).(string)
	if !ok || userID == "" {
		return fiber.NewError(fiber.StatusUnauthorized, "unauthorized")
	}

	payload, _ := json.Marshal(map[string]interface{}{
		"userId":    userID,
		"revokeAll": true,
	})
	h.fireAndForgetRevoke(c, payload)

	h.blacklistCurrentAccessToken(c)
	h.clearCookies(c)
	return c.SendStatus(fiber.StatusOK)
}

func (h *AuthHandler) fireAndForgetRevoke(c *fiber.Ctx, payload []byte) {
	httpReq, _ := http.NewRequestWithContext(c.UserContext(), http.MethodPost, h.userServiceURL+"/internal/auth/revoke-tokens", bytes.NewBuffer(payload))
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("X-Internal-Api-Key", h.internalAPIKey)
	resp, err := h.httpClient.Do(httpReq)
	if err == nil {
		resp.Body.Close()
	}
}

func (h *AuthHandler) blacklistCurrentAccessToken(c *fiber.Ctx) {
	jti, _ := c.Locals("jti").(string)
	tokenExpVal := c.Locals("tokenExp")
	if jti != "" && tokenExpVal != nil {
		if expTime, ok := tokenExpVal.(time.Time); ok {
			remaining := time.Until(expTime)
			if remaining > 0 {
				_ = h.redisClient.Set(c.UserContext(), "jti:"+jti, "1", remaining).Err()
			}
		}
	}
}

func (h *AuthHandler) clearCookies(c *fiber.Ctx) {
	c.Cookie(&fiber.Cookie{
		Name:     "access_token",
		Value:    "",
		HTTPOnly: true,
		Path:     "/",
		Expires:  time.Now().Add(-24 * time.Hour),
	})
	c.Cookie(&fiber.Cookie{
		Name:     "refresh_token",
		Value:    "",
		HTTPOnly: true,
		Path:     "/auth/refresh",
		Expires:  time.Now().Add(-24 * time.Hour),
	})
}
