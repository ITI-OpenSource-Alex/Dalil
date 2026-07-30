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
	"github.com/gofiber/websocket/v2"
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
	// Exam needs its own client. Submitting a Writing task blocks while the exam
	// service runs four criterion agents against the LLM — measured at ~50s
	// against AgentRouter — so the shared 10s client returned 502 while both
	// services were still working normally, an upstream timeout wearing an
	// upstream failure's costume. The other exam routes (get session, heartbeat)
	// return in milliseconds, so a longer ceiling costs them nothing.
	examClient := &http.Client{Timeout: 6 * time.Minute}
	examHandler := handlers.NewExamHandler(examClient, cfg.ExamServiceURL, cfg.InternalApiKey)
	notificationHandler := handlers.NewNotificationHandler(httpClient, cfg.NotificationServiceURL, cfg.InternalApiKey)
	examOwnership := middleware.NewExamSessionOwnership(
		redisClient,
		httpClient,
		cfg.ExamServiceURL,
		cfg.InternalApiKey,
		cfg.ExamOwnershipCacheTTL,
		logger,
	)
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
	speakingHandler := handlers.NewSpeakingHandler(httpClient, cfg.SpeakingServiceURL, cfg.InternalApiKey)
	speakingWSHandler, err := handlers.NewSpeakingWSHandler(cfg.SpeakingServiceURL, logger)
	if err != nil {
		return nil, err
	}
	// streamClient, not httpClient: RAG's /match scores every candidate program
	// sequentially, each with a potential LLM boost, so an uncached search does
	// not fit the shared 10s budget.
	opportunitiesHandler := handlers.NewOpportunitiesHandler(streamClient, cfg.RAGServiceURL, cfg.InternalApiKey)
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

	app.Delete("/users/:id/account", middleware.JWT(cfg.JWTSecret, redisClient, metrics), authHandler.DeleteAccount)
	app.Get("/users/:id/data-export", middleware.JWT(cfg.JWTSecret, redisClient, metrics), authHandler.DataExport)
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
	// Subscription policy is default-allow: only the Writing, CV and exam prep
	// routes named as paid features attach RequirePaid. Chat, chat history,
	// notifications and any future unnamed route remain free unless explicitly
	// changed. Exam prep moved to the paid side in GOA-059, where the whole
	// /api/exam group carries the gate rather than each route repeating it.
	api.Post("/writing/essays/upload", subscriptionMiddleware.RequirePaid, middleware.ValidateEssayTextLength(5000), writingHandler.UploadEssay)
	api.Post("/writing/cv/upload", subscriptionMiddleware.RequirePaid, writingHandler.UploadCV)
	api.Post("/writing/cv/review",
		subscriptionMiddleware.RequirePaid,
		middleware.AIRateLimiter(redisClient, "cv_review", cfg.CVReviewsPerHour, time.Hour, logger, metrics),
		writingHandler.ReviewCV)
	// The two flat /exam/listening routes that stood here are not dropped: GOA-059
	// re-registers them inside the exam group below, where they pick up the shared
	// paid gate, the start limiter and ownership validation.

	// Routes the frontend used to reach by other means. Chat posted to a Next.js
	// BFF route that was never built (BUG-044); exam and writing were called
	// directly on their service ports with INTERNAL_API_KEY published to the
	// browser in a NEXT_PUBLIC_ variable (BUG-046). Behind the Gateway the key
	// stays server-side and these paths gain JWT auth, rate limiting and
	// correlation IDs (BUG-029).
	api.Post("/chat",
		middleware.ValidateJSONFieldLength("message", 2000, logger, metrics),
		middleware.AIRateLimiter(redisClient, "chat", cfg.ChatQueriesPerHour, time.Hour, logger, metrics),
		streamHandler.Chat)
	api.Get("/chat/sessions/:sessionId/history", streamHandler.ChatHistory)
	// GOA-038. Inside the /api group, so erasure inherits JWT auth, rate
	// limiting and a correlation ID like every other call. A third "sessions"
	// namespace alongside /api/chat/sessions/... and /api/exam/sessions/... --
	// distinct paths that do not shadow each other, but worth GOA-132 knowing
	// about when it inventories routes.
	api.Delete("/sessions/memory", streamHandler.ChatMemory)

	// Exam prep route group (GOA-059). Every route below is paid-tier only and
	// inherits the /api chain above it: JWT, the 60/min request limiter and
	// subscription resolution.
	//
	// The paths are unchanged from when these routes were registered individually
	// -- the group only hoists the shared prefix and the shared gate, so no client
	// needs to change.
	exam := api.Group("/exam", subscriptionMiddleware.RequirePaid)
	examStartLimiter := middleware.ExamStartRateLimiter(redisClient, cfg.ExamStartLimitPerHour, metrics)

	// Session-opening routes share one hourly counter, so the ceiling is three
	// sessions per candidate per hour across every skill rather than three each.
	exam.Post("/sessions", examStartLimiter, examHandler.CreateSession)
	exam.Get("/listening/start", examStartLimiter, examHandler.StartListening)

	// Ownership is checked on the routes that read or mutate a named session's
	// outcome. GetSession and Heartbeat are left off deliberately: the Exam
	// service already scopes the heartbeat to X-User-Id and returns 403 itself,
	// and GetSession exposes no scores. Adding the middleware there would spend an
	// upstream round trip per poll for a check the upstream already performs.
	exam.Put("/sessions/:sessionId/submit", examOwnership.Validate, examHandler.SubmitSession)
	exam.Get("/sessions/:sessionId/result", examOwnership.Validate, examHandler.GetSessionResult)
	exam.Put("/listening/:sessionId/submit", examOwnership.Validate, examHandler.SubmitListening)
	// GOA-055: Reading-specific submit, needed for per_question_result and
	// section_breakdown that the generic submit above doesn't return.
	exam.Put("/reading/:sessionId/submit", examOwnership.Validate, examHandler.SubmitReadingSession)
	exam.Get("/sessions/:sessionId", examHandler.GetSession)
	exam.Patch("/sessions/:sessionId/heartbeat", examHandler.Heartbeat)
	// GOA-060. Registered flat as /api/exam/progress before GOA-059; it keeps the
	// same path inside the group. Ownership validation does not apply -- the route
	// takes no session id and the Exam service scopes the summary to X-User-Id.
	exam.Get("/progress", examHandler.GetProgress)

	// TODO(GOA-059): GET /api/exam/audio/:sessionId/:section is not implemented.
	// It would validate ownership (examOwnership.Validate) and then hand back the
	// section's S3 pre-signed URL, but the Exam service exposes no endpoint that
	// returns one: presigned URLs are minted inside create_listening_session and
	// returned only in the GET /exam/listening/start body, never persisted, and
	// GET /sessions/:id does not include them. The Gateway cannot presign on its
	// own -- it holds no S3 credentials, bucket name or audio_s3_key. Blocked on
	// an Exam service endpoint (owned by the exam team) along the lines of
	// GET /internal/sessions/{id}/audio/{section}; wire it here once that lands.

	api.Post("/writing/essays/:essayId/evaluate",
		subscriptionMiddleware.RequirePaid,
		middleware.AIRateLimiter(redisClient, "essay_evaluation", cfg.EssayEvalsPerHour, time.Hour, logger, metrics),
		streamHandler.WritingEvaluate)
	api.Get("/notifications", notificationHandler.List)

	// GOA-132: the last two flows that reached their services directly from the
	// browser (BUG-029). Speaking's socket was published as
	// PUBLIC_SPEAKING_WS_URL and its session routes as NEXT_PUBLIC_SPEAKING_API_URL,
	// both with no JWT check, no rate limit and no correlation ID.
	//
	// The session routes are the more urgent half: Speaking scopes GET
	// /sessions/{id} to a user only when a userId query parameter is present,
	// and the browser was supplying it -- so omitting it returned any user's
	// transcript. Inside this group userId comes from the token instead.
	api.Get("/speaking/sessions", speakingHandler.ListSessions)
	api.Get("/speaking/sessions/:sessionId", speakingHandler.GetSession)
	api.Post("/speaking/sessions/:sessionId/share", speakingHandler.CreateShareLink)
	// Mounted in the /api group so JWT validation, rate limiting and the
	// correlation ID all apply to the upgrade REQUEST itself. That is what
	// "authenticated at upgrade time, not after" means in practice, and it needs
	// no new auth code: middleware.JWT already falls back to the access_token
	// cookie, which browsers do send on a WebSocket handshake.
	api.Get("/speaking/ws", speakingWSHandler.Upgrade, websocket.New(speakingWSHandler.Proxy))
	// Public share reads are unauthenticated by design -- the recipient of a
	// share link has no account -- so this one sits outside the JWT group.
	app.Get("/speaking/sessions/public/:token", speakingHandler.GetPublicSession)

	api.Post("/opportunities/query",
		middleware.AIRateLimiter(redisClient, "opportunity_search", cfg.OpportunitySearchesPerHour, time.Hour, logger, metrics),
		opportunitiesHandler.Query)
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

