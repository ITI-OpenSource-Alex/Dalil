package main

import (
	"database/sql"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/handlers"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/gofiber/fiber/v2"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

type GatewayServer struct {
	App             *fiber.App
	dbPool          *sql.DB
	redisClient     *redis.Client
	shutdownTimeout time.Duration
}

func NewGatewayServer(cfg Config, logger zerolog.Logger) (*GatewayServer, error) {
	metrics, err := observability.NewMetrics()
	if err != nil {
		return nil, err
	}

	db, err := sql.Open("postgres", cfg.DatabaseURL)
	if err != nil {
		return nil, err
	}

	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}

	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(25)
	db.SetConnMaxLifetime(5 * time.Minute)

	redisOptions, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		db.Close()
		return nil, err
	}
	redisClient := redis.NewClient(redisOptions)

	app := fiber.New(fiber.Config{
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		ErrorHandler: middleware.ErrorHandler(logger),
	})

	startTime := time.Now()
	tokenService := gatewayauth.NewTokenService(cfg.JWTSecret, cfg.AccessTokenTTL, cfg.RefreshTokenTTL)
	repo := gatewayauth.NewRefreshTokenRepository(db)
	dbValidator := gatewayauth.NewDatabaseCredentialValidator(db)
	authHandler := handlers.NewAuthHandler(db, redisClient, repo, tokenService, dbValidator, metrics)

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
	return &GatewayServer{
		App:             app,
		dbPool:          db, // <-- Assign pool
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
	// Clean up database connection pool
	if s.dbPool != nil {
		if err := s.dbPool.Close(); err != nil && shutdownErr == nil {
			shutdownErr = err
		}
	}
	if s.redisClient != nil {
		if err := s.redisClient.Close(); err != nil && shutdownErr == nil {
			shutdownErr = err
		}
	}
	return shutdownErr
}
