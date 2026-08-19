// Package httpx provides the single shared HTTP transport for every outbound
// call the Speaking service makes.
//
// Sharing one *http.Transport is the whole point: connection pooling and
// keep-alive live on the Transport, not on the Client. Four evaluation agents
// firing concurrently at AgentRouter through four separately-constructed
// clients means four independent pools and, in practice, a fresh TLS handshake
// per request -- roughly 100-200ms each against a remote gateway, paid on every
// call rather than once per connection lifetime.
//
// It lives in its own leaf package because llm and tts both need it, and
// internal/speaking already imports agents -> llm. Putting the pool in
// internal/speaking would close that loop into an import cycle.
package httpx

import (
	"net/http"
	"time"
)

// sharedTransport is process-wide by design. http.Transport is safe for
// concurrent use and is explicitly documented as something you construct once
// and reuse; constructing one per client is the standard way to leak
// connections in Go.
var sharedTransport = &http.Transport{
	// The service talks to exactly two upstreams: AgentRouter and the local
	// speech sidecar. MaxIdleConns is a global ceiling, but MaxIdleConnsPerHost
	// is the number that actually binds here -- with two hosts, a per-host cap
	// below the concurrency level closes and reopens connections even though the
	// global ceiling is nowhere near reached. Go's default per-host value is 2,
	// which is lower than the 4 concurrent swarm agents.
	MaxIdleConns:        100,
	MaxIdleConnsPerHost: 50,
	IdleConnTimeout:     90 * time.Second,

	// Setting a custom Transport disables Go's automatic HTTP/2 upgrade.
	// http.DefaultTransport gets h2 for free; a hand-built one does not unless
	// this is set. That matters for AgentRouter specifically: four concurrent
	// agent requests multiplex onto a single h2 connection instead of opening
	// four, so the pool above stops being load-bearing at all.
	ForceAttemptHTTP2: true,

	// Bound the handshake itself, so a wedged TLS negotiation surfaces as an
	// error rather than consuming the caller's whole budget.
	TLSHandshakeTimeout:   10 * time.Second,
	ExpectContinueTimeout: 1 * time.Second,
}

// NewClient returns an *http.Client sharing the process-wide pooled transport,
// with a per-client overall timeout.
//
// Timeout stays per-client because the three callers have genuinely different
// deadlines -- CPU Whisper on a two-minute Part 2 answer is not the same budget
// as a local Piper synth call -- while the connection pool underneath is
// identical.
func NewClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout:   timeout,
		Transport: sharedTransport,
	}
}

// Transport exposes the shared transport for tests that need to assert every
// client is genuinely sharing one pool.
func Transport() *http.Transport { return sharedTransport }
