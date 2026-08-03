package main

import (
	"log"
	"os"
	"strconv"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/rs/zerolog"
	"github.com/valyala/fasthttp/fasthttpadaptor"
)

var (
	startTime = time.Now()
	version   = "0.1.0"

	requestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "goa_gateway_requests_total",
			Help: "Total HTTP requests handled by the gateway",
		},
		[]string{"route", "method", "status_code"},
	)
)

func init() {
	prometheus.MustRegister(requestsTotal)
}

func main() {
	logger := zerolog.New(os.Stdout).With().Timestamp().Logger()

	app := fiber.New(fiber.Config{
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
	})

	app.Use(func(c *fiber.Ctx) error {
		reqId := c.Get("X-Correlation-ID")
		if reqId == "" {
			reqId = uuid.NewString()

		}
		c.Set("X-Correlation-ID", reqId)
		start := time.Now()
		err := c.Next()
		latency := time.Since(start)
		status := c.Response().StatusCode()
		requestsTotal.WithLabelValues(c.Route().Path, c.Method(), strconv.Itoa(status)).Inc()
		logger.Info().
			Str("request_id", reqId).
			Str("route", c.Route().Path).
			Int("status", status).
			Dur("latency_ms", latency).
			Msg("request handled")

		return err
	})

	app.Get("/health", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"status":  "ok",
			"version": version,
			"uptime":  time.Since(startTime).String(),
		})
	})

	app.Get("/metrics", func(c *fiber.Ctx) error {
		handler := fasthttpadaptor.NewFastHTTPHandler(promhttp.Handler())
		handler(c.Context())
		return nil
	})

	log.Fatal(app.Listen(":8080"))
}
