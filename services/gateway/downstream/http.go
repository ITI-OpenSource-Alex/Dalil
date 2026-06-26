package downstream

import (
	"io"
	"net/http"

	"github.com/ITI-OpenSource-Alex/GOA/services/gateway/middleware"
	"github.com/gofiber/fiber/v2"
)

func NewRequest(c *fiber.Ctx, method string, url string, body io.Reader) (*http.Request, error) {
	req, err := http.NewRequest(method, url, body)
	if err != nil {
		return nil, err
	}

	ForwardCorrelationID(c, req)
	return req, nil
}

func ForwardCorrelationID(c *fiber.Ctx, req *http.Request) {
	if c == nil || req == nil {
		return
	}

	correlationID, _ := c.Locals(middleware.ContextKeyRequestID).(string)
	if correlationID == "" {
		return
	}

	req.Header.Set(middleware.HeaderCorrelationID, correlationID)
}
