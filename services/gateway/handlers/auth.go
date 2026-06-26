package handlers

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"errors"
	"os"
	"strings"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
	"golang.org/x/crypto/bcrypt"
)

type AuthHandler struct {
	db           *sql.DB
	redisClient  *redis.Client
	repo         *gatewayauth.RefreshTokenRepository
	tokenService *gatewayauth.TokenService
	validator    gatewayauth.CredentialValidator
	metrics      *observability.Metrics
}

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type refreshRequest struct {
	RefreshToken string `json:"refresh_token"`
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
	db *sql.DB,
	redisClient *redis.Client,
	repo *gatewayauth.RefreshTokenRepository,
	tokenService *gatewayauth.TokenService,
	validator gatewayauth.CredentialValidator,
	metrics *observability.Metrics,
) *AuthHandler {
	if validator == nil {
		validator = gatewayauth.StaticCredentialValidator{}
	}

	return &AuthHandler{
		db:           db,
		redisClient:  redisClient,
		repo:         repo,
		tokenService: tokenService,
		validator:    validator,
		metrics:      metrics,
	}
}

func (h *AuthHandler) Login(c *fiber.Ctx) error {
	var req loginRequest
	if err := c.BodyParser(&req); err != nil {
		return fiber.NewError(fiber.StatusBadRequest, "malformed login request")
	}

	req.Email = strings.TrimSpace(req.Email)
	if req.Email == "" || req.Password == "" {
		return fiber.NewError(fiber.StatusBadRequest, "email and password are required")
	}

	// 1. Validate credentials via Postgres validator
	user, err := h.validator.Validate(c.UserContext(), req.Email, req.Password)
	if err != nil {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "invalid credentials")
	}

	// 2. Generate Access Token JWT (includes jti automatically)
	accessToken, err := h.tokenService.NewAccessToken(user)
	if err != nil {
		return err
	}

	// 3. Generate secure refresh token (32-byte hex)
	rawRefreshToken, err := generateSecureToken()
	if err != nil {
		return err
	}

	// 4. Hashing refresh token using bcrypt
	hashedBytes, err := bcrypt.GenerateFromPassword([]byte(rawRefreshToken), bcrypt.DefaultCost)
	if err != nil {
		return err
	}
	tokenHash := string(hashedBytes)

	// Set expiresAt (30 days duration)
	expiresAt := time.Now().Add(30 * 24 * time.Hour)

	// Optional User-Agent for audit log device hint
	userAgent := c.Get("User-Agent")
	var deviceHint *string
	if userAgent != "" {
		deviceHint = &userAgent
	}

	// 5. Store hash in DB table
	tokenID, err := h.repo.Create(c.UserContext(), user.ID, tokenHash, expiresAt, deviceHint)
	if err != nil {
		return err
	}

	// Cookie secure configuration (local HTTP dev vs HTTPS prod)
	secure := os.Getenv("SECURE_COOKIES") == "true"

	// 6. Set access_token cookie (Path=/)
	c.Cookie(&fiber.Cookie{
		Name:     "access_token",
		Value:    accessToken,
		HTTPOnly: true,
		Secure:   secure,
		SameSite: "Lax",
		Path:     "/",
		Expires:  time.Now().Add(1 * time.Hour),
	})

	// 7. Set refresh_token cookie (Path=/auth/refresh for scoped boundary safety)
	c.Cookie(&fiber.Cookie{
		Name:     "refresh_token",
		Value:    tokenID + "." + rawRefreshToken,
		HTTPOnly: true,
		Secure:   secure,
		SameSite: "Lax",
		Path:     "/auth/refresh",
		Expires:  expiresAt,
	})

	return c.JSON(loginResponse{
		AccessToken:  accessToken,
		RefreshToken: tokenID + "." + rawRefreshToken,
		TokenType:    "Bearer",
		ExpiresIn:    int64(h.tokenService.AccessTokenTTL().Seconds()),
	})
}

func (h *AuthHandler) Refresh(c *fiber.Ctx) error {
	var req refreshRequest
	_ = c.BodyParser(&req)

	// Extract from cookie first, fallback to JSON body for tests
	refreshTokenValue := c.Cookies("refresh_token")
	if refreshTokenValue == "" {
		refreshTokenValue = strings.TrimSpace(req.RefreshToken)
	}

	if refreshTokenValue == "" {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusBadRequest, "refresh_token is required")
	}

	// Parse format: <token_id>.<raw_token_value>
	parts := strings.SplitN(refreshTokenValue, ".", 2)
	if len(parts) != 2 {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "invalid refresh token format")
	}
	tokenID := parts[0]
	rawToken := parts[1]

	// 1. Fetch DB record
	token, err := h.repo.FindByID(c.UserContext(), tokenID)
	if err != nil {
		h.metrics.RecordAuthFailure()
		if errors.Is(err, sql.ErrNoRows) {
			return fiber.NewError(fiber.StatusUnauthorized, "refresh token not found")
		}
		return err
	}

	// 2. Validate bcrypt hash
	err = bcrypt.CompareHashAndPassword([]byte(token.TokenHash), []byte(rawToken))
	if err != nil {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "invalid refresh token")
	}

	// 3. Replay attack validation check!
	if token.RevokedAt != nil {
		h.metrics.RecordAuthFailure()
		// Revoke ALL active sessions for this user ID immediately
		_ = h.repo.RevokeAll(c.UserContext(), token.UserID)
		return fiber.NewError(fiber.StatusUnauthorized, "token already revoked, session terminated")
	}

	// 4. Expiration check
	if time.Now().After(token.ExpiresAt) {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "refresh token expired")
	}

	// 5. Invalidate the current token in database
	err = h.repo.Revoke(c.UserContext(), tokenID)
	if err != nil && !errors.Is(err, gatewayauth.ErrTokenNotFound) {
		return err
	}

	// 6. Query email for user model mapping context
	var email string
	err = h.db.QueryRowContext(c.UserContext(), `SELECT email FROM users WHERE id = $1`, token.UserID).Scan(&email)
	if err != nil {
		return err
	}

	user := gatewayauth.User{
		ID:    token.UserID,
		Email: email,
	}

	// 7. Issue new tokens
	newAccessToken, err := h.tokenService.NewAccessToken(user)
	if err != nil {
		return err
	}

	newRawRefreshToken, err := generateSecureToken()
	if err != nil {
		return err
	}

	newHashedBytes, err := bcrypt.GenerateFromPassword([]byte(newRawRefreshToken), bcrypt.DefaultCost)
	if err != nil {
		return err
	}
	newTokenHash := string(newHashedBytes)

	// Rotate the window: set expiresAt to +30 days from now (resetting window)
	newExpiresAt := time.Now().Add(30 * 24 * time.Hour)

	newDeviceHint := token.DeviceHint
	userAgent := c.Get("User-Agent")
	if userAgent != "" {
		newDeviceHint = &userAgent
	}

	newTokenID, err := h.repo.Create(c.UserContext(), user.ID, newTokenHash, newExpiresAt, newDeviceHint)
	if err != nil {
		return err
	}

	secure := os.Getenv("SECURE_COOKIES") == "true"

	// Rewrite cookies
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
		Value:    newTokenID + "." + newRawRefreshToken,
		HTTPOnly: true,
		Secure:   secure,
		SameSite: "Lax",
		Path:     "/auth/refresh",
		Expires:  newExpiresAt,
	})

	return c.JSON(refreshResponse{
		AccessToken: newAccessToken,
		TokenType:   "Bearer",
		ExpiresIn:   int64(h.tokenService.AccessTokenTTL().Seconds()),
	})
}

func (h *AuthHandler) Logout(c *fiber.Ctx) error {
	// 1. Attempt database revocation for refresh token
	refreshTokenValue := c.Cookies("refresh_token")
	if refreshTokenValue != "" {
		parts := strings.SplitN(refreshTokenValue, ".", 2)
		if len(parts) == 2 {
			tokenID := parts[0]
			rawToken := parts[1]

			token, err := h.repo.FindByID(c.UserContext(), tokenID)
			if err == nil {
				err = bcrypt.CompareHashAndPassword([]byte(token.TokenHash), []byte(rawToken))
				if err == nil && token.RevokedAt == nil {
					_ = h.repo.Revoke(c.UserContext(), tokenID)
				}
			}
		}
	}

	// 2. Perform Redis Blacklist Write
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

	// 3. Clear both httpOnly cookies
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

	return c.SendStatus(fiber.StatusOK)
}

func (h *AuthHandler) LogoutAll(c *fiber.Ctx) error {
	userID, ok := c.Locals(middleware.ContextKeyUserID).(string)
	if !ok || userID == "" {
		return fiber.NewError(fiber.StatusUnauthorized, "unauthorized")
	}

	// 1. Revoke all refresh tokens in user_db
	_ = h.repo.RevokeAll(c.UserContext(), userID)

	// 2. Perform Redis Blacklist Write for current access token
	jti, _ := c.Locals("jti").(string)
	tokenExpVal := c.Locals("tokenExp")
	if jti != "" && tokenExpVal != nil {
		if expTime, _ := tokenExpVal.(time.Time); ok {
			remaining := time.Until(expTime)
			if remaining > 0 {
				_ = h.redisClient.Set(c.UserContext(), "jti:"+jti, "1", remaining).Err()
			}
		}
	}

	// 3. Clear cookies
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

	return c.SendStatus(fiber.StatusOK)
}

func generateSecureToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
