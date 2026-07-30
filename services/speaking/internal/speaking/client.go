package speaking

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/langfuse"
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

// swarmEvaluationTimeout bounds the 4-agent evaluation swarm. Every agent call
// traverses the AgentRouter gateway, measured at roughly 2.5s to over a minute
// per request, so the deadline has to clear the slow tail or the partial-result
// path never gets a single completed agent to work with. See BUG-038.
const swarmEvaluationTimeout = 60 * time.Second

// WSMessage abstracts websocket payloads to make concurrent writes safe
type WSMessage struct {
	Type    int
	Payload []byte
}

// TTSClient abstracts the ElevenLabs TTS operations for testing
type TTSClient interface {
	StreamTTS(ctx context.Context, text string, writeAudio func([]byte) error) error
}

// LangfuseClient abstracts the Langfuse batch operations for testing
type LangfuseClient interface {
	SendBatch(ctx context.Context, events []langfuse.IngestionEvent) error
}
type Client struct {
	id          string
	conn        *websocket.Conn
	send        chan WSMessage // Funnels all text and binary messages safely
	audioBuffer *bytes.Buffer
	bufferMutex sync.Mutex
	lastAudioAt time.Time
	e2eStart    time.Time
	ctx         context.Context
	cancel      context.CancelFunc
	speechURL   string
	// Session metrics tracking variables
	userID      string
	startTime   time.Time
	outcome     string
	lastTransMs int64
	// Swarm parameters
	initialized     bool
	questionPrompt  string
	questionType    string
	dbRepo          db.Repository
	llmClient       agents.LLMClient // Decoupled interface
	ttsClient       TTSClient        // Decoupled interface
	langfuseClient  LangfuseClient   // Decoupled interface
	traceID         string
	parentTraceSpan string
	firstTTSWritten int32 // atomic check
	firstTTSSentAt  time.Time
	// For testing mock
	transcribeFn func(audio []byte)
}

// HandleWebSocket upgrades connection and initializes clients/repos dependency injection using interfaces
func HandleWebSocket(w http.ResponseWriter, r *http.Request, cfg *Config, dbRepo db.Repository, llmClient agents.LLMClient, ttsClient TTSClient, lfClient LangfuseClient) {
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
	traceID, parentTraceSpan, hasParentTrace := langfuse.ParseTraceparent(
		r.URL.Query().Get("traceparent"),
	)
	if !hasParentTrace {
		traceID = strings.ReplaceAll(uuid.New().String(), "-", "")
		parentTraceSpan = ""
	}
	client := &Client{
		id:              uuid.New().String(),
		conn:            conn,
		send:            make(chan WSMessage, 256),
		audioBuffer:     buf,
		lastAudioAt:     time.Now(),
		ctx:             ctx,
		cancel:          cancel,
		speechURL:       cfg.SpeechServiceURL,
		userID:          "anonymous", // Defaults to anonymous, overridden upon first text packet
		startTime:       time.Now(),
		outcome:         "dropped", // default outcome unless completed/errored
		dbRepo:          dbRepo,
		llmClient:       llmClient,
		ttsClient:       ttsClient,
		langfuseClient:  lfClient,
		traceID:         traceID,
		parentTraceSpan: parentTraceSpan,
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

func (c *Client) sendErrorAndClose(reason string) {
	errPayload, _ := json.Marshal(map[string]string{
		"type":    "error",
		"message": reason,
	})
	c.conn.WriteMessage(websocket.TextMessage, errPayload)
	c.conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(1008, reason))
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

		if !c.initialized {
			// Enforce session_init is first
			if messageType != websocket.TextMessage {
				log.Warn().Str("session_id", c.id).Msg("Non-text frame received before session_init")
				c.sendErrorAndClose("Session not initialized. Expected session_init frame first.")
				break
			}

			var initMsg struct {
				Type           string `json:"type"`
				UserID         string `json:"userId"`
				QuestionPrompt string `json:"questionPrompt"`
				QuestionType   string `json:"questionType"`
			}
			err := json.Unmarshal(msg, &initMsg)
			if err != nil || initMsg.Type != "session_init" || initMsg.UserID == "" || initMsg.QuestionPrompt == "" || initMsg.QuestionType == "" {
				log.Warn().Str("session_id", c.id).Msg("Malformed session_init frame received")
				c.sendErrorAndClose("Invalid session_init payload.")
				break
			}

			c.userID = initMsg.UserID
			c.questionPrompt = initMsg.QuestionPrompt
			c.questionType = initMsg.QuestionType
			c.initialized = true
			log.Info().Str("session_id", c.id).Str("user_id", c.userID).Msg("Session initialized successfully")
			continue
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

			w, err := c.conn.NextWriter(message.Type)
			if err != nil {
				return
			}
			_, err = w.Write(message.Payload)
			if err != nil {
				return
			}

			if err := w.Close(); err != nil {
				return
			}

			// Capture exact stop time at network write completion of first binary TTS frame
			if message.Type == websocket.BinaryMessage && atomic.CompareAndSwapInt32(&c.firstTTSWritten, 0, 1) {
				c.firstTTSSentAt = time.Now()
				e2eDuration := time.Since(c.e2eStart)
				e2eLatencyMetric.Observe(float64(e2eDuration.Milliseconds()))
			}
		}
	}
}

// runEvaluationAndTTS coordinates evaluation, telemetry, audio streaming, and async persistence
func (c *Client) runEvaluationAndTTS(transcript string, transcriptionMs int64) {
	// 1. Run the parallel evaluation swarm under a deadline. Agents that finish
	// contribute; stragglers are marked TimedOut and excluded from the average.
	//
	// The budget was 3500ms, which no agent could meet: every call goes out
	// through the AgentRouter gateway, whose measured latency ranges from ~2.5s
	// to well over a minute. All four timed out on every session, so this path
	// always returned "Evaluation completely failed due to timeout" and the
	// partial-result machinery below was unreachable (BUG-038).
	//
	// swarmEvaluationTimeout is sized off that measured distribution. Reducing it
	// again needs a faster provider, not a smaller number.
	swarmCtx, swarmCancel := context.WithTimeout(c.ctx, swarmEvaluationTimeout)
	swarmCtx = context.WithValue(swarmCtx, "userID", c.userID)
	defer swarmCancel()

	swarmStart := time.Now()
	swarmRes, swarmErr := agents.EvaluateSwarm(swarmCtx, c.llmClient, c.questionPrompt, c.questionType, transcript)
	swarmDuration := time.Since(swarmStart)

	// Handle total swarm failure (all 4 agents timed out or errored)
	if swarmErr != nil || swarmRes.Status == "failed" {
		log.Error().Err(swarmErr).Str("session_id", c.id).Msg("Swarm evaluation completely failed")
		errPayload, _ := json.Marshal(map[string]string{
			"type":    "error",
			"message": "Evaluation completely failed due to timeout.",
		})
		c.send <- WSMessage{Type: websocket.TextMessage, Payload: errPayload}
		c.outcome = "error"
		return
	}

	// 2. Telemetry: Record band scores and LLM latency for completed agents (skip timed-out ones)
	var maxLLMLatency int64
	for name, dim := range swarmRes.Dimensions {
		if !dim.TimedOut {
			AgentBandScoreMetric.WithLabelValues(name).Observe(dim.Band)
			LlmFirstTokenMetric.Observe(float64(dim.LatencyMs)) // Log LLM response latency
			if dim.LatencyMs > maxLLMLatency {
				maxLLMLatency = dim.LatencyMs
			}
		}
	}

	// 3. Send Text Evaluation JSON over WebSocket
	evalPayload, err := json.Marshal(map[string]any{
		"type":             "evaluation",
		"status":           swarmRes.Status,
		"partial":          swarmRes.Partial,
		"overall_band":     swarmRes.OverallBand,
		"dimensions":       swarmRes.Dimensions,
		"overall_feedback": swarmRes.OverallFeedback,
	})
	if err == nil {
		c.send <- WSMessage{Type: websocket.TextMessage, Payload: evalPayload}
	}

	// 4. Stream synthesized audio voiceover via ElevenLabs
	ttsStart := time.Now()
	var firstTTSChunkTime time.Time

	ttsErr := c.ttsClient.StreamTTS(c.ctx, swarmRes.OverallFeedback, func(chunk []byte) error {
		if firstTTSChunkTime.IsZero() {
			firstTTSChunkTime = time.Now()
			// Record TTS time-to-first-audio latency
			ttsLatency := firstTTSChunkTime.Sub(ttsStart).Milliseconds()
			TtsFirstAudioMetric.Observe(float64(ttsLatency))
		}

		// Direct chunk forward to connection funnel
		c.send <- WSMessage{
			Type:    websocket.BinaryMessage,
			Payload: chunk,
		}
		return nil
	})

	// If TTS fails outright, degrade gracefully and notify the client
	if ttsErr != nil {
		log.Error().Err(ttsErr).Str("session_id", c.id).Msg("TTS streaming failed")
		c.send <- WSMessage{
			Type:    websocket.TextMessage,
			Payload: []byte(`{"type": "tts_unavailable"}`),
		}
	}

	// 5. Asynchronous DB save in a detached context (Disconnected safe)
	go func() {
		detachedCtx, detachedCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer detachedCancel()

		rawEval, _ := json.Marshal(swarmRes.Dimensions)
		sess := &db.SpeakingSession{
			ID:             c.id,
			UserID:         c.userID,
			QuestionPrompt: c.questionPrompt,
			QuestionType:   c.questionType,
			Transcript:     transcript,
			Evaluation:     rawEval,
			OverallBand:    swarmRes.OverallBand,
			CreatedAt:      time.Now(),
		}

		err := c.dbRepo.Create(detachedCtx, sess)
		if err != nil {
			log.Error().Err(err).Str("session_id", c.id).Msg("Non-fatal error: failed to persist session to database")
		}
	}()

	// 6. Asynchronous Langfuse auditing in a detached context
	go func() {
		detachedCtx, detachedCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer detachedCancel()

		events := make([]langfuse.IngestionEvent, 0, len(swarmRes.Dimensions)+2)
		if c.parentTraceSpan == "" {
			events = append(events, langfuse.IngestionEvent{
				ID:        c.id,
				Type:      "trace",
				Timestamp: time.Now(),
				Body: langfuse.TraceBody{
					ID:        c.traceID,
					Name:      "speaking_evaluation",
					UserID:    c.userID,
					SessionID: c.id,
					Metadata: map[string]any{
						"question_prompt": c.questionPrompt,
						"question_type":   c.questionType,
					},
				},
			})
		}

		speakingSpanID := strings.ReplaceAll(uuid.New().String(), "-", "")[:16]
		events = append(events, langfuse.IngestionEvent{
			ID:        speakingSpanID,
			Type:      "span",
			Timestamp: time.Now(),
			Body: langfuse.SpanBody{
				ID:                  speakingSpanID,
				TraceID:             c.traceID,
				ParentObservationID: c.parentTraceSpan,
				Name:                "speaking_evaluation",
				StartTime:           ttsStart.Add(-swarmDuration),
				EndTime:             ttsStart,
				Input:               transcript,
				Output:              map[string]any{"overall_band": swarmRes.OverallBand},
				Metadata: map[string]any{
					"session_id": c.id,
					"user_id":    c.userID,
				},
			},
		})

		for name, dim := range swarmRes.Dimensions {
			spanID := strings.ReplaceAll(uuid.New().String(), "-", "")[:16]
			metadata := map[string]any{
				"criterion": name,
				"timed_out": dim.TimedOut,
			}
			if !dim.TimedOut {
				metadata["band_score"] = dim.Band
			}

			events = append(events, langfuse.IngestionEvent{
				ID:        spanID,
				Type:      "generation",
				Timestamp: time.Now(),
				Body: langfuse.GenerationBody{
					ID:                  spanID,
					TraceID:             c.traceID,
					ParentObservationID: speakingSpanID,
					Name:                name,
					StartTime:           ttsStart.Add(-swarmDuration),
					EndTime:             ttsStart,
					Model:               "claude-3-5-haiku-20241022",
					Input:               transcript,
					Output:              dim.Feedback,
					Usage: map[string]int{
						"inputTokens":  dim.PromptTokens,
						"outputTokens": dim.CompletionTokens,
					},
					Metadata: metadata,
				},
			})
		}

		err := c.langfuseClient.SendBatch(detachedCtx, events)
		if err != nil {
			log.Error().Err(err).Str("session_id", c.id).Msg("Failed to report traces to Langfuse")
		}
	}()

	// 7. SLO Breach Check & Outcomes tracking
	c.outcome = "completed"

	var e2eLatency int64
	if !c.firstTTSSentAt.IsZero() {
		e2eLatency = c.firstTTSSentAt.Sub(c.e2eStart).Milliseconds()
	} else {
		e2eLatency = time.Since(c.e2eStart).Milliseconds()
	}

	llmLatency := swarmDuration.Milliseconds()
	var ttsLatency int64
	if !firstTTSChunkTime.IsZero() {
		ttsLatency = firstTTSChunkTime.Sub(ttsStart).Milliseconds()
	}

	if e2eLatency > 3000 {
		log.Error().
			Str("session_id", c.id).
			Int64("e2e_latency_ms", e2eLatency).
			Int64("transcription_ms", transcriptionMs).
			Int64("llm_ms", llmLatency).
			Int64("tts_ms", ttsLatency).
			Msg("SLO breach: Speaking evaluation pipeline exceeded 3000ms latency budget")
	}
}
