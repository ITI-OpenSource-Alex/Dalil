package main

import (
	"net/http"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/handlers"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

type GatewayServer struct {
	App             *fiber.App
	redisClient     *redis.Client
	shutdownTimeout time.Duration
}

func NewGatewayServer(cfg Config, logger zerolog.Logger) (*GatewayServer, error) {
	metrics, err := observability.NewMetrics()
	if err != nil {
		return nil, err
	}

	redisOptions, err := redis.ParseURL(cfg.RedisURL)

	if err != nil {
		return nil, err
	}

	redisClient := redis.NewClient(redisOptions)

	app := fiber.New(fiber.Config{
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		BodyLimit:    15 * 1024 * 1024,
		ErrorHandler: middleware.ErrorHandler(logger),
	})

	startTime := time.Now()
	tokenService := gatewayauth.NewTokenService(cfg.JWTSecret, cfg.AccessTokenTTL, cfg.RefreshTokenTTL)
	httpClient := &http.Client{Timeout: 10 * time.Second}
	authHandler := handlers.NewAuthHandler(redisClient, tokenService, metrics, httpClient, cfg.UserServiceURL, cfg.InternalApiKey)
	writingHandler := handlers.NewWritingHandler(httpClient, cfg.WritingServiceURL)

	app.Use(middleware.RequestID())
	app.Use(middleware.RequestLogger(logger, metrics))
	app.Get("/health", handlers.Health(startTime, cfg.Version))
	app.Get("/metrics", handlers.Metrics())

	// Public auth endpoints
	app.Post("/auth/login", authHandler.Login)
	app.Post("/auth/refresh", authHandler.Refresh)

	// Protected auth endpoints (gated by JWT middleware containing the Redis blacklist check)
	app.Post("/auth/logout", middleware.JWT(cfg.JWTSecret, redisClient, metrics), authHandler.Logout)
	app.Post("/auth/logout-all", middleware.JWT(cfg.JWTSecret, redisClient, metrics), authHandler.LogoutAll)
	api := app.Group("/api", middleware.JWT(cfg.JWTSecret, redisClient, metrics))
	api.Use(middleware.RateLimiter(redisClient, 60, metrics))
	api.Get("/ping", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok"})
	})
	
	app.Get("/admin/costs", handlers.AdminCosts(redisClient, cfg.BudgetUSD, cfg.CostPromptPer1M, cfg.CostCompletionPer1M))
	api.Post("/writing/essays/upload", middleware.ValidateEssayTextLength(5000), writingHandler.UploadEssay)
	api.Post("/writing/cv/upload", writingHandler.UploadCV)
	app.Post(
		"/cv/upload",
		middleware.JWT(cfg.JWTSecret, redisClient, metrics),
		middleware.RateLimiter(redisClient, 60, metrics),
		writingHandler.UploadCV,
	)

	return &GatewayServer{
		App:             app,
		redisClient:     redisClient,
		shutdownTimeout: cfg.ShutdownTimeout,
	}, nil
}
func NewServer(cfg Config, logger zerolog.Logger) (*fiber.App, error) {
	server, err := NewGatewayServer(cfg, logger)
	if err != nil {
		return nil, err
	}
	return server.App, nil
}
func (s *GatewayServer) Listen(addr string) error {
	return s.App.Listen(addr)
}
func (s *GatewayServer) Shutdown() error {
	var shutdownErr error
	if err := s.App.ShutdownWithTimeout(s.shutdownTimeout); err != nil {
		shutdownErr = err
	}
	if s.redisClient != nil {
		if err := s.redisClient.Close(); err != nil && shutdownErr == nil {
			shutdownErr = err
		}
	}
	return shutdownErr
}
