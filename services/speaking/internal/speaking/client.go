package speaking

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/telemetry"
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

	// GOA-034: daily speaking budget. Package-level because the Gateway never
	// sees this traffic -- there is no WebSocket proxy (BUG-029 / GOA-094), so
	// a speaking session bypasses every Gateway control by design and this is
	// the only place the limit can live.
	speakingQuota = telemetry.NewSpeakingQuota()
)

// swarmEvaluationTimeout bounds the 4-agent evaluation swarm. Every agent call
// traverses the AgentRouter gateway, measured at roughly 2.5s to over a minute
// per request, so the deadline has to clear the slow tail or the partial-result
// path never gets a single completed agent to work with. See BUG-038.
const swarmEvaluationTimeout = 60 * time.Second

// errClientGone unwinds a stream when the client can no longer be written to.
// It is a control signal, not a fault: it must not be logged as a TTS failure
// and must not produce a frame on a socket that has already gone away.
var errClientGone = errors.New("speaking: client connection is gone")

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
	// e2eStartNano is the unix-nano timestamp of the first audio byte of the
	// current utterance. Atomic rather than mutex-guarded because GOA-032 added
	// four swarm goroutines as readers alongside readPump (writer) and writePump
	// (reader) -- the previous unsynchronised time.Time was already a race and
	// would have become a busy one.
	e2eStartNano int64
	ctx          context.Context
	cancel       context.CancelFunc
	speechURL    string
	// Session metrics tracking variables
	userID string
	// outcome is written by the transcription goroutine and read by readPump's
	// cleanup, so it is atomic. Use setOutcome/getOutcome, never the field.
	outcome atomic.Value // string
	// correlationID ties this session to the Gateway request that opened it
	// (GOA-132). Falls back to the session id when Speaking is reached directly,
	// so the field is never absent and one grep follows a session end to end.
	correlationID string
	startTime     time.Time
	lastTransMs   int64
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
	// firstTTSSentNano and firstCriterionSent are written from writePump and the
	// swarm goroutines respectively and read from runEvaluationAndTTS, so both
	// are atomic.
	firstTTSSentNano   int64
	firstCriterionSent int32
	// For testing mock
	transcribeFn func(audio []byte)
}

// setOutcome and getOutcome guard c.outcome, which is written from the
// transcription goroutine (completed / error) and read from readPump's cleanup
// when it records goa_speaking_sessions_total. Without this the counter can be
// incremented against a torn read of the label.
func (c *Client) setOutcome(outcome string) { c.outcome.Store(outcome) }

func (c *Client) getOutcome() string {
	if v, ok := c.outcome.Load().(string); ok {
		return v
	}
	return "dropped"
}

// e2eElapsedMs reports milliseconds since the first audio byte of the current
// utterance, or 0 when no audio has been received yet.
func (c *Client) e2eElapsedMs() int64 {
	start := atomic.LoadInt64(&c.e2eStartNano)
	if start == 0 {
		return 0
	}
	return time.Since(time.Unix(0, start)).Milliseconds()
}

// sanitizeCorrelationID bounds an inbound correlation id before it reaches the
// structured logs.
//
// The header is attacker-controllable whenever Speaking is reachable directly
// on :8082, and it is written verbatim into every log line for the session. An
// unbounded, unfiltered value is a log-injection primitive -- the same reasoning
// applied to the security_event fields in GOA-034. Anything that is not a plain
// id-shaped token is discarded rather than truncated, because a mangled id is
// worse than an absent one: it correlates a session to the wrong request.
func sanitizeCorrelationID(raw string) string {
	if raw == "" || len(raw) > 64 {
		return ""
	}
	for _, r := range raw {
		isAllowed := (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') ||
			(r >= '0' && r <= '9') || r == '-' || r == '_'
		if !isAllowed {
			return ""
		}
	}
	return raw
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
	sessionID := uuid.New().String()
	correlationID := sanitizeCorrelationID(r.Header.Get("X-Correlation-ID"))
	if correlationID == "" {
		correlationID = sessionID
	}
	client := &Client{
		id:              sessionID,
		conn:            conn,
		send:            make(chan WSMessage, 256),
		audioBuffer:     buf,
		lastAudioAt:     time.Now(),
		ctx:             ctx,
		cancel:          cancel,
		speechURL:       cfg.SpeechServiceURL,
		userID:          "anonymous", // Defaults to anonymous, overridden upon first text packet
		correlationID:   correlationID,
		startTime:       time.Now(),
		dbRepo:          dbRepo,
		llmClient:       llmClient,
		ttsClient:       ttsClient,
		langfuseClient:  lfClient,
		traceID:         traceID,
		parentTraceSpan: parentTraceSpan,
	}
	// Default outcome unless the session completes or errors.
	client.setOutcome("dropped")
	client.transcribeFn = client.transcribeAudio
	log.Info().
		Str("session_id", client.id).
		Str("correlation_id", client.correlationID).
		Msg("New WebSocket connection established")
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
	sessionsTotalMetric.WithLabelValues(c.getOutcome()).Inc()
	duration := time.Since(c.startTime).Seconds()

	// GOA-034: the cost of a speaking session is its duration, which is only
	// knowable now. Recording at close and checking at open means a user can
	// always start one session that takes them over budget -- accepted
	// deliberately, because the alternative is cutting someone off
	// mid-sentence and one session of overrun is cheaper than that experience.
	speakingQuota.Record(context.Background(), c.userID, duration)

	goroutinesCount := runtime.NumGoroutine()

	log.Info().
		Str("session_id", c.id).
		Str("correlation_id", c.correlationID).
		Str("user_id", c.userID).
		Float64("duration_s", duration).
		Int64("transcription_ms", atomic.LoadInt64(&c.lastTransMs)).
		Int("goroutines_at_close", goroutinesCount).
		Str("outcome", c.getOutcome()).
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

			// GOA-034: daily speaking budget (OWASP LLM04).
			//
			// Checked here rather than at the WebSocket upgrade because this is
			// the first moment we know who is connecting -- the user id arrives
			// in this frame, not in the handshake.
			if allowed, spent := speakingQuota.Allow(c.ctx, c.userID); !allowed {
				log.Warn().
					Str("event", "SECURITY_EVENT").
					Str("event_type", "speaking_quota_exceeded").
					Str("severity", "MEDIUM").
					Str("user_id", c.userID).
					Str("correlation_id", c.id).
					Str("action_taken", "rejected").
					Int64("seconds_used", spent).
					Int("daily_limit_seconds", speakingQuota.DailySeconds).
					Msg("security_event")
				c.sendErrorAndClose("You have used your speaking practice time for today. Please come back tomorrow.")
				break
			}

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
				atomic.StoreInt64(&c.e2eStartNano, time.Now().UnixNano())
				// A new utterance resets the per-utterance "first" latches, so a
				// second answer on the same socket measures its own
				// time-to-first-criterion rather than reporting zero.
				atomic.StoreInt32(&c.firstCriterionSent, 0)
				atomic.StoreInt32(&c.firstTTSWritten, 0)
				atomic.StoreInt64(&c.firstTTSSentNano, 0)
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
				atomic.StoreInt64(&c.firstTTSSentNano, time.Now().UnixNano())
				if elapsed := c.e2eElapsedMs(); elapsed > 0 {
					e2eLatencyMetric.Observe(float64(elapsed))
				}
			}
		}
	}
}

// sendFrame queues one frame for writePump, which owns the socket.
//
// It never touches c.conn: this is called from the transcription goroutine and
// from all four swarm goroutines, and a direct write would race writePump. The
// bounded timer matters as much as the ctx arm -- a disconnected client whose
// send buffer has filled would otherwise wedge a swarm goroutine until the 60s
// evaluation deadline.
func (c *Client) sendFrame(msgType int, payload []byte) bool {
	sendTimer := time.NewTimer(2 * time.Second)
	defer sendTimer.Stop()
	select {
	case <-c.ctx.Done():
		return false
	case c.send <- WSMessage{Type: msgType, Payload: payload}:
		return true
	case <-sendTimer.C:
		log.Error().
			Str("session_id", c.id).
			Str("correlation_id", c.correlationID).
			Msg("Timed out queueing frame to client")
		return false
	}
}

// criterionFrame is one criterion's result, sent the moment its agent returns.
//
// Deliberately small and self-contained: each frame carries exactly one
// criterion and never re-sends earlier ones. Accumulating state across frames
// would turn four small messages into four progressively larger ones and
// recreate the wait-for-everything latency this ticket exists to remove.
type criterionFrame struct {
	Type      string   `json:"type"`
	Criterion string   `json:"criterion"`
	Band      *float64 `json:"band,omitempty"`
	Feedback  string   `json:"feedback"`
	Examples  []string `json:"examples,omitempty"`
	TimedOut  bool     `json:"timed_out"`
	ElapsedMs int64    `json:"elapsed_ms"`
}

// evaluationFrame is the final aggregate, sent after all four agents settle.
type evaluationFrame struct {
	Type            string                        `json:"type"`
	Status          string                        `json:"status"`
	Partial         bool                          `json:"partial"`
	CompletedCount  int                           `json:"completed_count"`
	OverallBand     *float64                      `json:"overall_band,omitempty"`
	Dimensions      map[string]agents.AgentResult `json:"dimensions"`
	OverallFeedback string                        `json:"overall_feedback"`
}

// onCriterionComplete streams one criterion to the client as its agent lands.
//
// Runs on the completing agent's goroutine (see agents.EvaluateSwarm), which is
// the whole point: the user sees Fluency while Pronunciation is still thinking.
func (c *Client) onCriterionComplete(ev agents.CriterionEvent) {
	// Three-valued, not two. "timed_out" alone cannot tell a slow provider from
	// a dead credential -- which is exactly the diagnosis this ticket is meant
	// to make possible, and exactly what a 2.8s "timeout" of all four agents
	// turned out to be.
	outcome := "completed"
	switch {
	case ev.Result.Error == agents.AgentErrorDeadline:
		outcome = "deadline"
	case ev.Result.TimedOut:
		outcome = "provider_error"
	}
	if ev.Result.TimedOut {
		log.Warn().
			Str("session_id", c.id).
			Str("correlation_id", c.correlationID).
			Str("criterion", ev.Criterion).
			Str("reason", outcome).
			Str("detail", ev.Result.Error).
			Int64("elapsed_ms", ev.ElapsedMs).
			Msg("Criterion did not complete")
	}
	criterionCompleteMetric.WithLabelValues(ev.Criterion, outcome).Observe(float64(ev.ElapsedMs))

	frame := criterionFrame{
		Type:      "criterion",
		Criterion: ev.Criterion,
		Feedback:  ev.Result.Feedback,
		Examples:  ev.Result.Examples,
		TimedOut:  ev.Result.TimedOut,
		ElapsedMs: ev.ElapsedMs,
	}
	// Band is omitted for a timed-out criterion rather than sent as 0.0. A
	// client rendering "Band 0.0" for an agent that never scored is BUG-055
	// again, one layer out.
	if !ev.Result.TimedOut {
		band := ev.Result.Band
		frame.Band = &band
	}

	payload, err := json.Marshal(frame)
	if err != nil {
		log.Error().Err(err).Str("session_id", c.id).Msg("Failed to marshal criterion frame")
		return
	}
	if !c.sendFrame(websocket.TextMessage, payload) {
		return
	}

	// First criterion of this utterance wins the race and records the metric the
	// user-perceived SLO is written against.
	if atomic.CompareAndSwapInt32(&c.firstCriterionSent, 0, 1) {
		if elapsed := c.e2eElapsedMs(); elapsed > 0 {
			timeToFirstCriterionMetric.Observe(float64(elapsed))
			c.checkSLO(budgetFirstCriterion, float64(elapsed))
		}
	}
}

// runEvaluationAndTTS coordinates evaluation, telemetry, audio streaming, and async persistence
func (c *Client) runEvaluationAndTTS(transcript string, transcriptionMs int64, features *agents.ProsodyFeatures) {
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
	// onCriterionComplete streams each criterion as it lands. Everything below
	// this call is the aggregate, which the client no longer has to wait for
	// before showing the user something.
	swarmRes, swarmErr := agents.EvaluateSwarm(
		swarmCtx, c.llmClient, c.questionPrompt, c.questionType, transcript,
		features,
		c.onCriterionComplete,
	)
	swarmDuration := time.Since(swarmStart)

	// Handle total swarm failure (all 4 agents timed out or errored)
	if swarmErr != nil || swarmRes.Status == "failed" {
		log.Error().Err(swarmErr).
			Str("session_id", c.id).
			Str("correlation_id", c.correlationID).
			Msg("Swarm evaluation completely failed")
		errPayload, _ := json.Marshal(map[string]string{
			"type":    "error",
			"message": "Evaluation completely failed due to timeout.",
		})
		c.sendFrame(websocket.TextMessage, errPayload)
		c.setOutcome("error")
		return
	}

	// 2. Telemetry: Record band scores and LLM latency for completed agents (skip timed-out ones)
	var maxLLMLatency int64
	for name, dim := range swarmRes.Dimensions {
		if !dim.TimedOut {
			AgentBandScoreMetric.WithLabelValues(name).Observe(dim.Band)
			// FirstTokenMs, not LatencyMs -- see AgentResult. A zero means the
			// stream produced no text block to timestamp, which is not a
			// measurement of zero and must not be observed as one.
			if dim.FirstTokenMs > 0 {
				LlmFirstTokenMetric.Observe(float64(dim.FirstTokenMs))
			}
			if dim.LatencyMs > maxLLMLatency {
				maxLLMLatency = dim.LatencyMs
			}
		}
	}

	// 3. Send the aggregate evaluation frame. overall_band is absent entirely
	// when fewer than 3 criteria completed (BUG-040).
	evalPayload, err := json.Marshal(evaluationFrame{
		Type:            "evaluation",
		Status:          swarmRes.Status,
		Partial:         swarmRes.Partial,
		CompletedCount:  swarmRes.CompletedCount,
		OverallBand:     swarmRes.OverallBand,
		Dimensions:      swarmRes.Dimensions,
		OverallFeedback: swarmRes.OverallFeedback,
	})
	if err == nil {
		c.sendFrame(websocket.TextMessage, evalPayload)
	}

	// 4. Stream the synthesized voiceover from the local Piper sidecar.
	ttsStart := time.Now()
	var firstTTSChunkTime time.Time

	ttsErr := c.ttsClient.StreamTTS(c.ctx, swarmRes.OverallFeedback, func(chunk []byte) error {
		if firstTTSChunkTime.IsZero() {
			firstTTSChunkTime = time.Now()
			// Record TTS time-to-first-audio latency
			ttsLatency := firstTTSChunkTime.Sub(ttsStart).Milliseconds()
			TtsFirstAudioMetric.Observe(float64(ttsLatency))
		}

		// Copy before queueing. chunk aliases the TTS client's reusable 4KB read
		// buffer, which the next Read overwrites the instant this returns --
		// handing it straight to writePump gave the socket a buffer whose
		// contents had already changed. Audible as clipped or garbled audio, and
		// a genuine data race that `go test -race` flags.
		payload := make([]byte, len(chunk))
		copy(payload, chunk)

		if !c.sendFrame(websocket.BinaryMessage, payload) {
			// The client is gone or wedged. Returning an error unwinds the read
			// loop instead of pumping the remaining audio into a channel nobody
			// is draining.
			return errClientGone
		}
		return nil
	})

	// If TTS fails outright, degrade gracefully and notify the client.
	//
	// A client that disconnected mid-stream is not a TTS failure and gets no
	// frame -- the socket it would be written to is the thing that went away.
	// That arrives two ways: sendFrame refusing (errClientGone) or, when the
	// disconnect cancels c.ctx first, the upstream body read failing with
	// "context canceled". Both are the user closing a tab. Logging either at
	// ERROR fills the log with fake incidents and teaches the team to skim past
	// the real ones.
	clientLeft := errors.Is(ttsErr, errClientGone) || c.ctx.Err() != nil
	if ttsErr != nil && !clientLeft {
		log.Error().Err(ttsErr).
			Str("session_id", c.id).
			Str("correlation_id", c.correlationID).
			Msg("TTS streaming failed")
		c.sendFrame(websocket.TextMessage, []byte(`{"type":"tts_unavailable"}`))
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
			// Nullable on purpose. Persisting 0.0 for a session that never
			// reached 3 completed criteria would put the BUG-040 defect back --
			// history would list "Band 0.0" for an evaluation that produced no
			// band at all. The column allows NULL (migration 003) and the API
			// returns null, which a UI can render as "not scored".
			OverallBand: swarmRes.OverallBand,
			CreatedAt:   time.Now(),
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

	// 7. Latency breakdown + SLO check.
	c.setOutcome("completed")

	e2eStart := atomic.LoadInt64(&c.e2eStartNano)
	firstTTS := atomic.LoadInt64(&c.firstTTSSentNano)
	var e2eLatency int64
	switch {
	case e2eStart == 0:
		// No audio was ever received (mock/no-speech-URL path). There is no
		// end-to-end interval to report, and reporting 0 would drag the
		// histogram toward a latency nothing achieved.
		e2eLatency = 0
	case firstTTS != 0:
		e2eLatency = (firstTTS - e2eStart) / int64(time.Millisecond)
	default:
		e2eLatency = c.e2eElapsedMs()
	}

	llmLatency := swarmDuration.Milliseconds()
	var ttsLatency int64
	if !firstTTSChunkTime.IsZero() {
		ttsLatency = firstTTSChunkTime.Sub(ttsStart).Milliseconds()
	}

	// Per-criterion timings, keyed by criterion, so one log line answers "which
	// agent was slow" without a join against the metrics. Recorded in
	// CriterionOrder rather than by ranging the map, so the field order is
	// stable across requests and a human can diff two lines by eye.
	criterionMs := make(map[string]int64, len(agents.CriterionOrder))
	firstTokenMs := make(map[string]int64, len(agents.CriterionOrder))
	for _, name := range agents.CriterionOrder {
		dim := swarmRes.Dimensions[name]
		criterionMs[name] = dim.LatencyMs
		firstTokenMs[name] = dim.FirstTokenMs
	}

	// Unconditional, not only-on-breach. The acceptance criteria ask for the
	// breakdown per request; a breakdown you only get once things are already
	// broken cannot show you the distribution moving before it breaks.
	log.Info().
		Str("session_id", c.id).
		Str("correlation_id", c.correlationID).
		Str("user_id", c.userID).
		Int64("e2e_latency_ms", e2eLatency).
		Int64("transcription_ms", transcriptionMs).
		Int64("llm_ms", llmLatency).
		Interface("llm_first_token_ms", firstTokenMs).
		Interface("criterion_complete_ms", criterionMs).
		Int64("tts_first_audio_ms", ttsLatency).
		Int("criteria_completed", swarmRes.CompletedCount).
		Bool("partial", swarmRes.Partial).
		Msg("Speaking evaluation latency breakdown")

	if e2eLatency > 0 {
		c.checkSLO(budgetE2E, float64(e2eLatency))
	}
}
