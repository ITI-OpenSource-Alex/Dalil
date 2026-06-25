package handlers

import (
	"github.com/gofiber/fiber/v2"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/valyala/fasthttp/fasthttpadaptor"
)

func Metrics() fiber.Handler {
	handler := fasthttpadaptor.NewFastHTTPHandler(promhttp.Handler())

	return func(c *fiber.Ctx) error {
		c.Set(fiber.HeaderContentType, fiber.MIMETextPlainCharsetUTF8)
		handler(c.Context())
		return nil
	}
}
