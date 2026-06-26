package handlers

import (
	"strings"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
)

type AuthHandler struct {
	validator    gatewayauth.CredentialValidator
	tokenService *gatewayauth.TokenService
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
	tokenService *gatewayauth.TokenService,
	validator gatewayauth.CredentialValidator,
	metrics *observability.Metrics,
) *AuthHandler {
	if validator == nil {
		validator = gatewayauth.StaticCredentialValidator{}
	}

	return &AuthHandler{
		validator:    validator,
		tokenService: tokenService,
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

	user, err := h.validator.Validate(req.Email, req.Password)
	if err != nil {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "invalid credentials")
	}

	accessToken, err := h.tokenService.NewAccessToken(user)
	if err != nil {
		return err
	}

	refreshToken, err := h.tokenService.NewRefreshToken(user)
	if err != nil {
		return err
	}

	return c.JSON(loginResponse{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		TokenType:    "Bearer",
		ExpiresIn:    int64(h.tokenService.AccessTokenTTL().Seconds()),
	})
}

func (h *AuthHandler) Refresh(c *fiber.Ctx) error {
	var req refreshRequest
	if err := c.BodyParser(&req); err != nil {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusBadRequest, "malformed refresh request")
	}

	refreshToken := strings.TrimSpace(req.RefreshToken)
	if refreshToken == "" {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusBadRequest, "refresh_token is required")
	}

	claims, err := h.tokenService.ParseRefreshToken(refreshToken)
	if err != nil {
		h.metrics.RecordAuthFailure()
		return fiber.NewError(fiber.StatusUnauthorized, "invalid refresh token")
	}

	accessToken, err := h.tokenService.NewAccessToken(gatewayauth.User{
		ID:    claims.Subject,
		Email: claims.Email,
	})
	if err != nil {
		return err
	}

	return c.JSON(refreshResponse{
		AccessToken: accessToken,
		TokenType:   "Bearer",
		ExpiresIn:   int64(h.tokenService.AccessTokenTTL().Seconds()),
	})
}
