package speaking

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/contract"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/interview"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/rs/zerolog/log"
)

const (
	SpeakingProtocolVersion = 3
	maxInterviewTurnBytes   = 12 * 1024 * 1024
	interviewerTimeout      = 2 * time.Second
)

type InterviewStore interface {
	CreateInterview(context.Context, db.InterviewSession) error
	SaveInterviewTurn(context.Context, string, interview.Turn) error
	SaveInterviewProgress(context.Context, string, interview.Snapshot, string, bool) error
	LoadInterview(context.Context, string, string) (*db.InterviewSession, error)
	RecentInterviewCueIDs(context.Context, string, int) ([]string, error)
}

type InterviewSocketDeps struct {
	Config       *Config
	Sessions     db.Repository
	Store        InterviewStore
	ScoringLLM   agents.LLMClient
	Transcriber  TurnTranscriber
	Voice        ExaminerVoice
	Bank         *interview.Bank
	Followups    *interview.FollowupEngine
	Timing       interview.Timing
	Now          func() time.Time
	Part3MaxTurn int
}

type interviewInitFrame struct {
	Type            string `json:"type"`
	ProtocolVersion int    `json:"protocolVersion"`
	UserID          string `json:"userId"`
	AudioFormat     string `json:"audioFormat"`
	ResumeSessionID string `json:"resumeSessionId,omitempty"`
}

type interviewInbound struct {
	messageType int
	payload     []byte
	err         error
}

type interviewSocket struct {
	id          string
	userID      string
	audioFormat string
	conn        *websocket.Conn
	ctx         context.Context
	cancel      context.CancelFunc
	writeMu     sync.Mutex
	deps        InterviewSocketDeps
	session     *interview.Session
	selection   interview.Selection
	audio       bytes.Buffer
	startedAt   time.Time
	pendingLong *interview.CandidateTurn
}

type interviewTurnSink struct {
	store     InterviewStore
	sessionID string
}

func (s interviewTurnSink) SaveTurn(ctx context.Context, turn interview.Turn) error {
	return s.store.SaveInterviewTurn(ctx, s.sessionID, turn)
}

func HandleInterviewWebSocket(w http.ResponseWriter, r *http.Request, deps InterviewSocketDeps) {
	if deps.Config == nil || deps.Store == nil || deps.Transcriber == nil || deps.Voice == nil || deps.Bank == nil {
		http.Error(w, "Speaking interviewer is not configured", http.StatusServiceUnavailable)
		return
	}
	if atomic.LoadInt32(&activeConns) >= int32(deps.Config.MaxConnections) {
		http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
		return
	}
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	atomic.AddInt32(&activeConns, 1)
	activeConnectionsMetric.Inc()
	ctx, cancel := context.WithCancel(context.Background())
	socket := &interviewSocket{
		id: uuid.NewString(), conn: conn, ctx: ctx, cancel: cancel,
		deps: deps, startedAt: time.Now(),
	}
	defer socket.close()
	conn.SetReadLimit(maxInterviewTurnBytes)

	messageType, payload, err := conn.ReadMessage()
	if err != nil || messageType != websocket.TextMessage {
		socket.writePolicyError("invalid_session_init", "Expected session_init as the first text frame.")
		return
	}
	var init interviewInitFrame
	if err := json.Unmarshal(payload, &init); err != nil || init.Type != "session_init" || init.UserID == "" {
		socket.writePolicyError("invalid_session_init", "Invalid session_init payload.")
		return
	}
	if init.ProtocolVersion != SpeakingProtocolVersion {
		socket.writePolicyError("unsupported_protocol", fmt.Sprintf("Speaking protocol v%d is required; received v%d.", SpeakingProtocolVersion, init.ProtocolVersion))
		return
	}
	format, err := normalizeAudioFormat(init.AudioFormat)
	if err != nil {
		socket.writePolicyError("invalid_audio_format", err.Error())
		return
	}
	// GOA-030. When the Gateway proxied this upgrade it asserts the identity it
	// validated the JWT for, and that always wins over the frame's own field.
	//
	// The frame's userId is client-controlled. Sessions are persisted and listed
	// by this value and the daily quota is keyed on it, so trusting the frame
	// let a caller both write sessions under someone else's id and mint a fresh
	// id per connection to escape the quota entirely.
	//
	// The fallback to init.UserID is deliberate and is NOT a hole in the
	// production path: :8082 is not published past the Gateway, and the header
	// is set on every proxied upgrade. It keeps the direct-connection callers
	// working -- the Go WebSocket E2E suite and the k6 scenarios, which dial the
	// service without a Gateway in front of them.
	socket.userID = strings.TrimSpace(r.Header.Get("X-User-Id"))
	if socket.userID == "" {
		socket.userID = init.UserID
	}
	socket.audioFormat = format
	if allowed, _ := speakingQuota.Allow(ctx, socket.userID); !allowed {
		socket.writePolicyError("quota_exceeded", "You have used your speaking practice time for today. Please come back tomorrow.")
		return
	}

	if err := socket.initialize(init.ResumeSessionID); err != nil {
		socket.sendError("session_initialization_failed", err.Error())
		return
	}
	socket.prewarmSelectedQuestions()
	socket.sendJSON(map[string]any{"type": "session_started", "session_id": socket.id, "resumed": init.ResumeSessionID != ""})
	if init.ResumeSessionID == "" {
		outputs, err := socket.session.Start(ctx)
		if err != nil {
			socket.sendError("interview_start_failed", err.Error())
			return
		}
		if err := socket.persistProgress(false); err != nil || !socket.emit(outputs) {
			return
		}
	} else if !socket.emit(socket.resumeOutputs()) {
		return
	}

	inbound := make(chan interviewInbound, 16)
	go func() {
		for {
			typ, data, readErr := conn.ReadMessage()
			select {
			case inbound <- interviewInbound{messageType: typ, payload: data, err: readErr}:
			case <-ctx.Done():
				return
			}
			if readErr != nil {
				return
			}
		}
	}()

	var timer *time.Timer
	for {
		timerC := (<-chan time.Time)(nil)
		deadline := socket.session.Deadline()
		if !deadline.IsZero() {
			wait := time.Until(deadline)
			if deps.Now != nil {
				wait = deadline.Sub(deps.Now())
			}
			if wait < 0 {
				wait = 0
			}
			if timer == nil {
				timer = time.NewTimer(wait)
			} else {
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				timer.Reset(wait)
			}
			timerC = timer.C
		} else if timer != nil {
			timer.Stop()
		}

		select {
		case <-ctx.Done():
			return
		case <-timerC:
			if !socket.handleTimer() {
				return
			}
		case message := <-inbound:
			if message.err != nil {
				return
			}
			complete, ok := socket.handleInbound(message)
			if !ok {
				return
			}
			if complete {
				socket.evaluateAndPersist()
				return
			}
		}
	}
}

func (s *interviewSocket) prewarmSelectedQuestions() {
	voice, ok := s.deps.Voice.(interface {
		Prewarm(context.Context, []VoicePrompt)
	})
	if !ok {
		return
	}
	prompts := make([]VoicePrompt, 0)
	for _, topic := range s.selection.Part1Topics {
		for _, question := range topic.Questions {
			prompts = append(prompts, VoicePrompt{Key: question.ID, Text: question.Text})
		}
	}
	for _, question := range s.selection.Cue.RoundingOff {
		prompts = append(prompts, VoicePrompt{Key: question.ID, Text: question.Text})
	}
	for _, question := range s.selection.Part3Seeds {
		prompts = append(prompts, VoicePrompt{Key: question.ID, Text: question.Text})
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
		defer cancel()
		voice.Prewarm(ctx, prompts)
	}()
}

func (s *interviewSocket) initialize(resumeID string) error {
	now := s.deps.Now
	if now == nil {
		now = time.Now
	}
	timing := s.deps.Timing
	if timing == (interview.Timing{}) {
		timing = interview.DefaultTiming()
	}
	maxTurns := s.deps.Part3MaxTurn
	if maxTurns <= 0 {
		maxTurns = 4
	}
	if resumeID != "" {
		record, err := s.deps.Store.LoadInterview(s.ctx, resumeID, s.userID)
		if err != nil {
			return fmt.Errorf("resume interview: %w", err)
		}
		if record.Status != "active" {
			return fmt.Errorf("interview is already %s", record.Status)
		}
		s.id = record.ID
		s.audioFormat = record.AudioFormat
		s.selection = record.Selection
		s.session, err = interview.RestoreSession(record.Selection, timing, now,
			interviewTurnSink{s.deps.Store, s.id}, s.deps.Followups, maxTurns, record.Snapshot)
		return err
	}

	recent, err := s.deps.Store.RecentInterviewCueIDs(s.ctx, s.userID, 10)
	if err != nil {
		return err
	}
	s.selection, err = s.deps.Bank.Select(s.id, recent)
	if err != nil {
		return err
	}
	s.session, err = interview.NewAdaptiveSession(s.selection, timing, now,
		interviewTurnSink{s.deps.Store, s.id}, s.deps.Followups, maxTurns)
	if err != nil {
		return err
	}
	return s.deps.Store.CreateInterview(s.ctx, db.InterviewSession{
		ID: s.id, UserID: s.userID, Status: "active",
		BankVersion: s.selection.BankVersion, BankSHA256: s.selection.BankSHA256,
		CueID: s.selection.Cue.CueID, VoiceID: s.deps.Voice.VoiceID(),
		AudioFormat: s.audioFormat, Selection: s.selection,
		Snapshot: s.session.Snapshot(), CreatedAt: now(),
	})
}

func (s *interviewSocket) handleInbound(message interviewInbound) (bool, bool) {
	if message.messageType == websocket.BinaryMessage {
		if !stateAcceptsAudio(s.session.State()) {
			s.sendError("audio_not_accepted", "The current interview stage does not accept candidate audio.")
			return false, true
		}
		if s.audio.Len()+len(message.payload) > maxInterviewTurnBytes {
			s.sendError("turn_too_large", "This answer exceeded the maximum recording size.")
			return false, false
		}
		_, _ = s.audio.Write(message.payload)
		return false, true
	}
	if message.messageType != websocket.TextMessage {
		return false, true
	}
	var control struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(message.payload, &control); err != nil {
		s.sendError("invalid_control_frame", "Could not read the interview control frame.")
		return false, true
	}
	var outputs []interview.Output
	var err error
	switch control.Type {
	case "ready":
		outputs, err = s.session.Handle(s.ctx, interview.Event{Type: interview.EventReady})
	case "prep_complete":
		outputs, err = s.session.Handle(s.ctx, interview.Event{Type: interview.EventPrepComplete})
	case "abandon":
		outputs, err = s.session.Handle(s.ctx, interview.Event{Type: interview.EventAbandon})
	case "audio_end":
		return s.finishCandidateTurn()
	default:
		s.sendError("unknown_control_frame", "Unsupported interview control frame.")
		return false, true
	}
	if err != nil {
		s.sendError("invalid_transition", err.Error())
		return false, true
	}
	partial := control.Type == "abandon"
	if err := s.persistProgress(partial); err != nil || !s.emit(outputs) {
		return false, false
	}
	return s.session.State() == interview.StateComplete, true
}

func (s *interviewSocket) finishCandidateTurn() (bool, bool) {
	if s.audio.Len() == 0 {
		s.sendError("empty_turn", "No audio was received for this answer.")
		return false, true
	}
	audio := append([]byte(nil), s.audio.Bytes()...)
	s.audio.Reset()
	transcription, err := s.deps.Transcriber.TranscribeTurn(s.ctx, audio, s.audioFormat)
	if err != nil {
		s.sendError("transcription_failed", "Transcription is unavailable right now. Please try this answer again.")
		return false, true
	}
	questionID := s.session.Snapshot().CurrentQuestionID
	s.sendJSON(map[string]any{"type": "transcript", "question_id": questionID, "text": transcription.Text, "isFinal": true})
	candidate := interview.CandidateTurn{
		Text: transcription.Text, DurationS: transcription.DurationS, Words: transcription.Words,
	}
	if s.pendingLong != nil && s.session.State() == interview.StatePart2LongTurn {
		candidate = joinCandidateTurns(*s.pendingLong, candidate)
		s.pendingLong = nil
	}
	outputs, err := s.session.Handle(s.ctx, interview.Event{
		Type:      interview.EventAudioEnd,
		Candidate: candidate,
	})
	if errors.Is(err, interview.ErrLongTurnTooShort) {
		s.pendingLong = &candidate
		timing := s.deps.Timing
		if timing == (interview.Timing{}) {
			timing = interview.DefaultTiming()
		}
		minimumEndsAt := s.session.Snapshot().LongTurnStartedAt.Add(timing.LongTurnMin)
		s.sendJSON(map[string]any{"type": "long_turn_continue", "remaining_s": max(0, int(time.Until(minimumEndsAt).Seconds()+1))})
		return false, true
	}
	if err != nil {
		s.sendError("turn_rejected", err.Error())
		return false, true
	}
	if err := s.persistProgress(false); err != nil || !s.emit(outputs) {
		return false, false
	}
	return s.session.State() == interview.StateComplete, true
}

func (s *interviewSocket) handleTimer() bool {
	var candidate interview.CandidateTurn
	if s.session.State() == interview.StatePart2LongTurn && s.audio.Len() > 0 {
		audio := append([]byte(nil), s.audio.Bytes()...)
		s.audio.Reset()
		transcription, err := s.deps.Transcriber.TranscribeTurn(s.ctx, audio, s.audioFormat)
		if err != nil {
			s.sendError("transcription_failed", "The long turn could not be transcribed.")
			return false
		}
		candidate = interview.CandidateTurn{Text: transcription.Text, DurationS: transcription.DurationS, Words: transcription.Words}
		s.sendJSON(map[string]any{"type": "transcript", "question_id": s.session.Snapshot().CurrentQuestionID, "text": transcription.Text, "isFinal": true})
	}
	if s.pendingLong != nil {
		candidate = joinCandidateTurns(*s.pendingLong, candidate)
		s.pendingLong = nil
	}
	outputs, err := s.session.Handle(s.ctx, interview.Event{Type: interview.EventTimerExpired, Candidate: candidate})
	if err != nil {
		s.sendError("timer_transition_failed", err.Error())
		return false
	}
	if err := s.persistProgress(false); err != nil {
		return false
	}
	return s.emit(outputs)
}

func (s *interviewSocket) emit(outputs []interview.Output) bool {
	for _, output := range outputs {
		if !s.sendJSON(output) {
			return false
		}
		if output.Type != "examiner_turn" {
			continue
		}
		audio, err := s.deps.Voice.Audio(s.ctx, output.QuestionID, output.Text)
		if err != nil {
			s.sendJSON(map[string]any{"type": "tts_unavailable", "turn_id": output.TurnID})
		} else if !s.sendFrame(websocket.BinaryMessage, audio) {
			return false
		}
		if !s.sendJSON(map[string]any{"type": "examiner_audio_end", "turn_id": output.TurnID}) {
			return false
		}
	}
	return true
}

func (s *interviewSocket) persistProgress(partial bool) error {
	status := "active"
	if s.session.State() == interview.StateComplete {
		status = "complete"
	}
	if err := s.deps.Store.SaveInterviewProgress(s.ctx, s.id, s.session.Snapshot(), status, partial); err != nil {
		s.sendError("persistence_failed", "Interview progress could not be saved.")
		return err
	}
	return nil
}

func (s *interviewSocket) resumeOutputs() []interview.Output {
	snapshot := s.session.Snapshot()
	part := 1
	if snapshot.State == interview.StatePart2Cue || snapshot.State == interview.StatePart2Prep || snapshot.State == interview.StatePart2LongTurn || snapshot.State == interview.StatePart2Rounding {
		part = 2
	} else if snapshot.State == interview.StatePart3Question || snapshot.State == interview.StateComplete {
		part = 3
	}
	outputs := []interview.Output{{Type: "session_resumed", Part: part, Text: string(snapshot.State)}}
	if snapshot.State == interview.StatePart2Prep {
		outputs = append(outputs,
			interview.Output{Type: "cue_card", CueID: s.selection.Cue.CueID, Topic: s.selection.Cue.Topic, Prompts: s.selection.Cue.Prompts, ClosingPrompt: s.selection.Cue.ClosingPrompt},
			interview.Output{Type: "prep_start", DurationS: int(time.Until(snapshot.Deadline).Seconds()), EndsAt: snapshot.Deadline},
		)
		return outputs
	}
	if snapshot.State == interview.StatePart2LongTurn {
		return append(outputs, interview.Output{Type: "long_turn_start", MinS: 0, MaxS: int(time.Until(snapshot.Deadline).Seconds()), EndsAt: snapshot.Deadline})
	}
	// The cue card is on screen for the whole of Part 2, and the client keys the
	// turn below against it, so it has to be restored before the turn is.
	if snapshot.State == interview.StatePart2Cue {
		outputs = append(outputs, interview.Output{
			Type: "cue_card", CueID: s.selection.Cue.CueID, Topic: s.selection.Cue.Topic,
			Prompts: s.selection.Cue.Prompts, ClosingPrompt: s.selection.Cue.ClosingPrompt,
		})
	}
	// Replay the last examiner turn, whatever it was.
	//
	// Matching on CurrentQuestionID instead misses precisely the states that
	// carry no question: part1_intro (the greeting) and part2_cue (the card
	// being read out). Both of those are waiting on `ready`, and the client only
	// sends `ready` in response to an examiner turn — so emitting nothing left
	// both sides waiting on each other with the examiner silent, which is how a
	// reload during the greeting killed the session for good.
	//
	// ExpectsResponse is derived from the state rather than assumed: telling the
	// client to record in a state that refuses candidate audio ends the session
	// with audio_not_accepted.
	for i := len(snapshot.Transcript.Turns) - 1; i >= 0; i-- {
		turn := snapshot.Transcript.Turns[i]
		if turn.Speaker != interview.SpeakerExaminer {
			continue
		}
		outputs = append(outputs, interview.Output{
			Type: "examiner_turn", TurnID: turn.TurnID, Part: turn.Part,
			QuestionID: turn.QuestionID, Text: turn.Text,
			ExpectsResponse: stateAcceptsAudio(snapshot.State),
		})
		break
	}
	return outputs
}

func (s *interviewSocket) evaluateAndPersist() {
	transcript := s.session.Transcript()
	candidateText := transcript.CandidateText()
	if candidateText == "" || s.deps.ScoringLLM == nil {
		s.sendJSON(map[string]any{"type": "evaluation", "status": "insufficient_evidence", "completed_count": 0, "dimensions": map[string]any{}})
		s.persistEvaluation(candidateText, nil)
		return
	}
	features := candidateProsody(transcript)
	if part2 := candidateProsodyForPart(transcript, 2); part2 != nil {
		s.sendJSON(map[string]any{
			"type": "part_prosody", "part": 2, "speech_duration_s": part2.SpeechDurationS,
			"words_per_minute": part2.WordsPerMinute, "pause_ratio": part2.PauseRatio,
			"long_pause_count": part2.LongPauseCount,
		})
	}
	result, err := agents.EvaluateSwarm(s.ctx, s.deps.ScoringLLM, s.selection.Cue.Topic, "full_interview", candidateText, features, func(event agents.CriterionEvent) {
		frame := criterionFrame{Type: "criterion", Criterion: event.Criterion, Feedback: event.Result.Feedback, Examples: event.Result.Examples, TimedOut: event.Result.TimedOut, ElapsedMs: event.ElapsedMs}
		if !event.Result.TimedOut {
			band := event.Result.Band
			frame.Band = &band
		}
		s.sendJSON(frame)
	})
	if err != nil {
		s.sendError("evaluation_failed", "The interview was saved, but scoring is unavailable right now.")
		s.persistEvaluation(candidateText, nil)
		return
	}
	s.sendJSON(evaluationFrame{Type: "evaluation", Status: result.Status, Partial: result.Partial, CompletedCount: result.CompletedCount, OverallBand: result.OverallBand, Dimensions: result.Dimensions, OverallFeedback: result.OverallFeedback})
	s.persistEvaluation(candidateText, &result)
}

func (s *interviewSocket) persistEvaluation(candidateText string, result *agents.SwarmResult) {
	if s.deps.Sessions == nil {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	evaluation := json.RawMessage(`{}`)
	var overallBand *float64
	if result != nil {
		evaluation, _ = json.Marshal(result.Dimensions)
		overallBand = result.OverallBand
	}
	createdAt := time.Now()
	if err := s.deps.Sessions.Create(ctx, &db.SpeakingSession{
		ID: s.id, UserID: s.userID, QuestionPrompt: s.selection.Cue.Topic,
		QuestionType: "full_interview", Transcript: candidateText,
		Evaluation: evaluation, OverallBand: overallBand, CreatedAt: createdAt,
	}); err != nil || result == nil {
		return
	}
	canonical := agents.CanonicalizeSwarm(*result, agents.CanonicalMeta{
		EvaluationID: s.id, Mode: contract.ModePractice, CreatedAt: createdAt.UTC(),
		ScorerVersion: scorerVersion(), LLMProvider: "agentrouter",
		LLMModel: EffectiveLLMModel(s.deps.ScoringLLM),
	})
	renderable := contract.BuildRenderable(canonical, candidateText)
	payload, err := json.Marshal(renderable)
	if err != nil {
		return
	}
	claims := 0
	for _, criterion := range renderable.Criteria {
		claims += len(criterion.Claims)
	}
	_ = s.deps.Sessions.SaveExplanation(ctx, &db.SpeakingExplanation{
		SessionID: s.id, Renderable: payload, RubricID: canonical.Provenance.RubricID,
		RubricVersion: canonical.Provenance.RubricVersion, RubricSHA256: canonical.Provenance.RubricSHA256,
		ScorerVersion: canonical.Provenance.ScorerVersion, LLMModel: canonical.Provenance.LLMModel,
		ClaimCount: claims, WithheldCount: renderable.WithheldCount(), CreatedAt: createdAt,
	})
}

func candidateProsody(transcript interview.Transcript) *agents.ProsodyFeatures {
	return candidateProsodyForPart(transcript, 0)
}

func candidateProsodyForPart(transcript interview.Transcript, part int) *agents.ProsodyFeatures {
	words := make([]agents.Word, 0)
	var duration float64
	for _, turn := range transcript.Turns {
		if turn.Speaker != interview.SpeakerCandidate || (part != 0 && turn.Part != part) {
			continue
		}
		turnDuration := turn.EndS - turn.StartS
		for _, word := range turn.Words {
			words = append(words, agents.Word{Word: word.Word, Start: duration + word.StartS, End: duration + word.EndS, Probability: word.Probability})
		}
		duration += turnDuration
	}
	features, ok := agents.ComputeProsody(words, duration)
	if !ok {
		return nil
	}
	return &features
}

func stateAcceptsAudio(state interview.State) bool {
	switch state {
	case interview.StatePart1Question, interview.StatePart2LongTurn, interview.StatePart2Rounding, interview.StatePart3Question:
		return true
	default:
		return false
	}
}

func joinCandidateTurns(first, second interview.CandidateTurn) interview.CandidateTurn {
	words := append([]interview.WordTiming(nil), first.Words...)
	for _, word := range second.Words {
		word.StartS += first.DurationS
		word.EndS += first.DurationS
		words = append(words, word)
	}
	text := first.Text
	if text != "" && second.Text != "" {
		text += " "
	}
	text += second.Text
	return interview.CandidateTurn{
		Text: text, AudioRef: first.AudioRef, Words: words,
		DurationS: first.DurationS + second.DurationS,
	}
}

func (s *interviewSocket) sendJSON(value any) bool {
	payload, err := json.Marshal(value)
	return err == nil && s.sendFrame(websocket.TextMessage, payload)
}

func (s *interviewSocket) sendError(code, message string) {
	s.sendJSON(map[string]any{"type": "error", "code": code, "message": message})
}

func (s *interviewSocket) sendFrame(messageType int, payload []byte) bool {
	if s.ctx.Err() != nil {
		return false
	}
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	_ = s.conn.SetWriteDeadline(time.Now().Add(2 * time.Second))
	if err := s.conn.WriteMessage(messageType, payload); err != nil {
		s.cancel()
		return false
	}
	return true
}

func (s *interviewSocket) writePolicyError(code, message string) {
	_ = s.conn.WriteJSON(map[string]any{"type": "error", "code": code, "message": message, "expected_protocol": SpeakingProtocolVersion})
	_ = s.conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.ClosePolicyViolation, message))
}

func (s *interviewSocket) close() {
	s.cancel()
	_ = s.conn.Close()
	atomic.AddInt32(&activeConns, -1)
	activeConnectionsMetric.Dec()
	if s.userID != "" {
		speakingQuota.Record(context.Background(), s.userID, time.Since(s.startedAt).Seconds())
	}
	log.Info().Str("session_id", s.id).Str("user_id", s.userID).Msg("Interview WebSocket closed")
}
