package main

import (
	"context"
	"net/http"
	"time"

	gatewayauth "github.com/ITI-OpenSource-Alex/GOA/services/gateway/auth"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/handlers"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/observability"
	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
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
	examHandler := handlers.NewExamHandler(httpClient, cfg.ExamServiceURL, cfg.InternalApiKey)
	notificationHandler := handlers.NewNotificationHandler(httpClient, cfg.NotificationServiceURL, cfg.InternalApiKey)
	subscriptionMiddleware := middleware.NewSubscriptionMiddleware(
		redisClient,
		httpClient,
		cfg.UserServiceURL,
		cfg.InternalApiKey,
		cfg.SubscriptionUpgradeURL,
		cfg.SubscriptionCacheTTL,
		logger,
	)
	// Streaming paths need their own client: the shared one has a 10s timeout,
	// which would sever a chat or essay-evaluation stream mid-flight. A speaking
	// evaluation alone has been measured at ~77s.
	streamClient := &http.Client{Timeout: 5 * time.Minute}
	// llmClient (streamClient) for CV review: a model call cannot finish inside
	// the shared 10s timeout.
	writingHandler := handlers.NewWritingHandler(httpClient, streamClient, cfg.WritingServiceURL)
	streamHandler := handlers.NewStreamHandler(
		streamClient, cfg.OrchestrationServiceURL, cfg.WritingServiceURL, cfg.InternalApiKey,
	)
	awsOptions := []func(*awsconfig.LoadOptions) error{
		awsconfig.WithRegion(cfg.AWSRegion),
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(context.Background(), awsOptions...)
	if err != nil {
		return nil, err
	}
	ingestionSQS := sqs.NewFromConfig(awsCfg, func(options *sqs.Options) {
		if cfg.AWSEndpointURL != "" {
			options.BaseEndpoint = aws.String(cfg.AWSEndpointURL)
		}
	})

	// CORS. Without this the browser's preflight got 405 and every call from the
	// frontend failed with net::ERR_FAILED -- login, chat, uploads, exam, all of
	// it. The gateway had no OPTIONS handler and sent no Access-Control headers,
	// so the UI could never reach the backend from a browser at all (BUG-043).
	//
	// AllowCredentials is required because auth rides on HttpOnly cookies, and the
	// CORS spec forbids pairing that with a wildcard origin -- hence an explicit
	// allow-list rather than "*". CORS_ALLOWED_ORIGINS is comma-separated so
	// staging and production can add their own without a code change.
	app.Use(cors.New(cors.Config{
		AllowOrigins:     cfg.CORSAllowedOrigins,
		AllowMethods:     "GET,POST,PUT,PATCH,DELETE,OPTIONS",
		AllowHeaders:     "Origin,Content-Type,Accept,Authorization,X-Correlation-ID,X-Internal-Api-Key,X-Admin-Key",
		ExposeHeaders:    "X-Correlation-ID",
		AllowCredentials: true,
	}))
	app.Use(middleware.RequestID())
	app.Use(middleware.RequestLogger(logger, metrics))
	app.Get("/health", handlers.Health(startTime, cfg.Version))
	app.Get("/metrics", handlers.Metrics())

	// Public auth endpoints
	app.Post("/users", authHandler.Register)
	app.Post("/auth/login", authHandler.Login)
	app.Post("/auth/refresh", authHandler.Refresh)
	app.Post("/auth/forgot-password", authHandler.ForgotPassword)
	app.Post("/auth/reset-password", authHandler.ResetPassword)
	app.Get("/auth/verify-email/:token", authHandler.VerifyEmail)

	// Protected auth endpoints (gated by JWT middleware containing the Redis blacklist check)
	app.Post("/auth/logout", middleware.JWT(cfg.JWTSecret, redisClient, metrics), authHandler.Logout)
	app.Post("/auth/logout-all", middleware.JWT(cfg.JWTSecret, redisClient, metrics), authHandler.LogoutAll)

`tapp.Delete("/users/:id/account", middleware.JWT(cfg.JWTSecret, redisClient, metrics), authHandler.DeleteAccount)
`tapp.Get("/users/:id/data-export", middleware.JWT(cfg.JWTSecret, redisClient, metrics), authHandler.DataExport)
	// Register the API admin route before the broad /api JWT middleware. This
	// endpoint is machine-administered with X-Admin-Key and must not also require
	// a user session.
	apiAdmin := app.Group("/api/admin", middleware.AdminKey(cfg.AdminAPIKey))
	apiAdmin.Post(
		"/ingestion/run",
		handlers.AdminIngestionRun(ingestionSQS, cfg.IngestionQueueURL),
	)
	api := app.Group("/api", middleware.JWT(cfg.JWTSecret, redisClient, metrics))
	api.Use(middleware.RateLimiter(redisClient, 60, metrics))
	api.Use(subscriptionMiddleware.ResolveSubscription)
	api.Get("/ping", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok"})
	})

	admin := app.Group("/admin", middleware.AdminKey(cfg.AdminAPIKey))
	admin.Get("/costs", handlers.AdminCosts(
		redisClient,
		cfg.BudgetUSD,
		cfg.LLMPricingJSON,
		cfg.CostPromptPer1M,
		cfg.CostCompletionPer1M,
	))
	// Subscription policy is default-allow: only the Writing and CV routes named
	// as paid features attach RequirePaid. Chat, chat history, notifications,
	// exams and any future unnamed route remain free unless explicitly changed.
	api.Post("/writing/essays/upload", subscriptionMiddleware.RequirePaid, middleware.ValidateEssayTextLength(5000), writingHandler.UploadEssay)
	api.Post("/writing/cv/upload", subscriptionMiddleware.RequirePaid, writingHandler.UploadCV)
	api.Post("/writing/cv/review", subscriptionMiddleware.RequirePaid, writingHandler.ReviewCV)
	api.Get("/exam/listening/start", examHandler.StartListening)
	api.Put("/exam/listening/:sessionId/submit", examHandler.SubmitListening)

	// Routes the frontend used to reach by other means. Chat posted to a Next.js
	// BFF route that was never built (BUG-044); exam and writing were called
	// directly on their service ports with INTERNAL_API_KEY published to the
	// browser in a NEXT_PUBLIC_ variable (BUG-046). Behind the Gateway the key
	// stays server-side and these paths gain JWT auth, rate limiting and
	// correlation IDs (BUG-029).
	api.Post("/chat", streamHandler.Chat)
	api.Get("/chat/sessions/:sessionId/history", streamHandler.ChatHistory)
	// GOA-038. Inside the /api group, so erasure inherits JWT auth, rate
	// limiting and a correlation ID like every other call. A third "sessions"
	// namespace alongside /api/chat/sessions/... and /api/exam/sessions/... --
	// distinct paths that do not shadow each other, but worth GOA-132 knowing
	// about when it inventories routes.
	api.Delete("/sessions/memory", streamHandler.ChatMemory)
	api.Post("/exam/sessions", examHandler.CreateSession)
	api.Get("/exam/sessions/:sessionId", examHandler.GetSession)
	api.Put("/exam/sessions/:sessionId/submit", examHandler.SubmitSession)
	api.Get("/exam/sessions/:sessionId/result", examHandler.GetSessionResult)
	api.Patch("/exam/sessions/:sessionId/heartbeat", examHandler.Heartbeat)
	// GOA-055: Reading-specific submit, needed for per_question_result and
	// section_breakdown that the generic submit above doesn't return.
	api.Put("/exam/reading/:sessionId/submit", examHandler.SubmitReadingSession)
	api.Post("/writing/essays/:essayId/evaluate", subscriptionMiddleware.RequirePaid, streamHandler.WritingEvaluate)
	api.Get("/notifications", notificationHandler.List)
	app.Post(
		"/cv/upload",
		middleware.JWT(cfg.JWTSecret, redisClient, metrics),
		middleware.RateLimiter(redisClient, 60, metrics),
		subscriptionMiddleware.ResolveSubscription,
		subscriptionMiddleware.RequirePaid,
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

