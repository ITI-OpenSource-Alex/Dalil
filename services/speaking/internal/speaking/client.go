package speaking

import (
	"bytes"
	"context"
	"net/http"
	"runtime"
	"sync"
	"sync/atomic"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/rs/zerolog/log"
)

var (
	upgrader = websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin: func(r *http.Request) bool {
			return true // Allow connections from any origin for development
		},
	}

	activeConns int32
)

type Client struct {
	id          string
	conn        *websocket.Conn
	send        chan []byte
	audioBuffer *bytes.Buffer
	bufferMutex sync.Mutex
	lastAudioAt time.Time
	e2eStart    time.Time
	ctx         context.Context
	cancel      context.CancelFunc
	apiKey      string

	// Session metrics tracking variables
	userID      string
	startTime   time.Time
	outcome     string
	lastTransMs int64

	//For testing mock
	transcribeFn func(audio []byte)
}

func HandleWebSocket(w http.ResponseWriter, r *http.Request, cfg *Config) {
	currentConns := atomic.LoadInt32(&activeConns)
	if currentConns >= int32(cfg.MaxConnections) {
		log.Warn().Msg("Max connections reached, rejecting connection")
		http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
		return
	}
	atomic.AddInt32(&activeConns, 1)
	activeConnectionsMetric.Inc() // Increment Prometheus active connections

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		atomic.AddInt32(&activeConns, -1)
		activeConnectionsMetric.Dec()
		log.Error().Err(err).Msg("Failed to upgrade WebSocket connection")
		return
	}

	ctx, cancel := context.WithCancel(context.Background())

	buf := bufferPool.Get().(*bytes.Buffer)
	buf.Reset()

	userID := r.URL.Query().Get("user_id")
	if userID == "" {
		userID = "anonymous"
	}

	client := &Client{
		id:          uuid.New().String(),
		conn:        conn,
		send:        make(chan []byte, 256),
		audioBuffer: buf,
		lastAudioAt: time.Now(),
		ctx:         ctx,
		cancel:      cancel,
		apiKey:      cfg.ElevenLabsAPIKey,
		userID:      userID,
		startTime:   time.Now(),
		outcome:     "dropped", // default state unless completed or errored
	}
	client.transcribeFn = client.transcribeAudio

	log.Info().Str("session_id", client.id).Msg("New WebSocket connection established")

	go client.writePump()
	go client.readPump()
	go client.vadTicker()
}

func (c *Client) cleanup() {
	c.cancel()
	c.conn.Close()

	atomic.AddInt32(&activeConns, -1)
	activeConnectionsMetric.Dec()
	c.bufferMutex.Lock()

	buf := c.audioBuffer
	c.audioBuffer = nil
	c.bufferMutex.Unlock()

	if buf != nil {
		if buf.Cap() <= 512*1024 {
			bufferPool.Put(buf)
		}
	}

	// Increment final session outcome counter
	sessionsTotalMetric.WithLabelValues(c.outcome).Inc()
	duration := time.Since(c.startTime).Seconds()
	goroutinesCount := runtime.NumGoroutine()

	log.Info().
		Str("session_id", c.id).
		Str("user_id", c.userID).
		Float64("duration_s", duration).
		Int64("transcription_ms", atomic.LoadInt64(&c.lastTransMs)).
		Int("goroutines_at_close", goroutinesCount).
		Str("outcome", c.outcome).
		Msg("WebSocket connection closed")
}

func (c *Client) readPump() {
	defer c.cleanup()
	c.conn.SetReadLimit(512 * 1024) // 512KB max message size
	for {
		messageType, msg, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Error().Err(err).Str("session_id", c.id).Msg("WebSocket read error")
			}
			break
		}

		if messageType == websocket.BinaryMessage {
			c.bufferMutex.Lock()
			if c.audioBuffer == nil {
				c.bufferMutex.Unlock()
				break
			}
			if c.audioBuffer.Len() == 0 {
				c.e2eStart = time.Now()
			}
			c.audioBuffer.Write(msg)
			c.lastAudioAt = time.Now()
			c.bufferMutex.Unlock()
		}
	}
}

func (c *Client) writePump() {
	for {
		select {
		case <-c.ctx.Done():
			return
		case message, ok := <-c.send:
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			w, err := c.conn.NextWriter(websocket.TextMessage)
			if err != nil {
				return
			}
			w.Write(message)

			if err := w.Close(); err != nil {
				return
			}
		}
	}
}
