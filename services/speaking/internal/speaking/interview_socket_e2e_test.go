package speaking

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sync"
	"testing"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/db"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/interview"
	"github.com/gorilla/websocket"
)

type memoryInterviewStore struct {
	mu      sync.Mutex
	records map[string]db.InterviewSession
	turns   map[string][]interview.Turn
}

func newMemoryInterviewStore() *memoryInterviewStore {
	return &memoryInterviewStore{records: make(map[string]db.InterviewSession), turns: make(map[string][]interview.Turn)}
}

func (m *memoryInterviewStore) CreateInterview(_ context.Context, record db.InterviewSession) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.records[record.ID] = record
	return nil
}

func (m *memoryInterviewStore) SaveInterviewTurn(_ context.Context, sessionID string, turn interview.Turn) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for index := range m.turns[sessionID] {
		if m.turns[sessionID][index].TurnID == turn.TurnID {
			m.turns[sessionID][index] = turn
			return nil
		}
	}
	m.turns[sessionID] = append(m.turns[sessionID], turn)
	return nil
}

func (m *memoryInterviewStore) SaveInterviewProgress(_ context.Context, sessionID string, snapshot interview.Snapshot, status string, partial bool) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	record := m.records[sessionID]
	record.Snapshot, record.Status, record.Partial = snapshot, status, partial
	m.records[sessionID] = record
	return nil
}

func (m *memoryInterviewStore) LoadInterview(_ context.Context, sessionID, userID string) (*db.InterviewSession, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	record, ok := m.records[sessionID]
	if !ok || record.UserID != userID {
		return nil, db.ErrSessionNotFound
	}
	copy := record
	return &copy, nil
}

func (m *memoryInterviewStore) RecentInterviewCueIDs(context.Context, string, int) ([]string, error) {
	return nil, nil
}

type deterministicTranscriber struct {
	mu    sync.Mutex
	calls int
}

func (t *deterministicTranscriber) TranscribeTurn(_ context.Context, _ []byte, _ string) (TurnTranscription, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.calls++
	return TurnTranscription{
		Text: "Candidate answer for turn " + time.Duration(t.calls).String(), DurationS: 10,
		Words: []interview.WordTiming{{Word: "Candidate", StartS: 0, EndS: .4, Probability: .95}, {Word: "answer", StartS: .5, EndS: .9, Probability: .94}},
	}, nil
}

type instantVoice struct{ calls int }

func (v *instantVoice) VoiceID() string { return "test/voice" }
func (v *instantVoice) Audio(context.Context, string, string) ([]byte, error) {
	v.calls++
	return []byte("RIFF-test-audio"), nil
}

type adaptiveQuestionGenerator struct{ calls int }

func (g *adaptiveQuestionGenerator) GenerateFollowup(context.Context, interview.FollowupRequest) (string, error) {
	g.calls++
	return "How could this topic affect communities in scenario " + time.Duration(g.calls).String() + "?", nil
}

type alwaysOnTopic struct{}

func (alwaysOnTopic) OnTopic(context.Context, string, []interview.Question) (bool, error) {
	return true, nil
}

type recordingSessionRepo struct {
	*mockDBRepo
	created chan *db.SpeakingSession
}

func (r *recordingSessionRepo) Create(_ context.Context, session *db.SpeakingSession) error {
	copy := *session
	r.created <- &copy
	return nil
}

func TestInterviewProtocolV3EndToEnd(t *testing.T) {
	bank, err := interview.LoadDefaultBank()
	if err != nil {
		t.Fatal(err)
	}
	store := newMemoryInterviewStore()
	transcriber := &deterministicTranscriber{}
	voice := &instantVoice{}
	generator := &adaptiveQuestionGenerator{}
	repo := &recordingSessionRepo{mockDBRepo: &mockDBRepo{}, created: make(chan *db.SpeakingSession, 1)}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		HandleInterviewWebSocket(w, r, InterviewSocketDeps{
			Config: &Config{MaxConnections: 10}, Sessions: repo, Store: store,
			ScoringLLM: &mockLLMClient{}, Transcriber: transcriber, Voice: voice, Bank: bank,
			Followups:    &interview.FollowupEngine{Generator: generator, TopicChecker: alwaysOnTopic{}, Policy: interview.DefaultFollowupPolicy()},
			Timing:       interview.Timing{Part1Expected: time.Second, Part2Expected: time.Second, Part3Expected: time.Second, Prep: 5 * time.Millisecond, LongTurnMin: 5 * time.Millisecond, LongTurnMax: 30 * time.Millisecond},
			Part3MaxTurn: 4,
		})
	}))
	defer server.Close()
	u, _ := url.Parse(server.URL)
	u.Scheme = "ws"
	conn, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	_ = conn.SetReadDeadline(time.Now().Add(15 * time.Second))
	if err := conn.WriteJSON(map[string]any{"type": "session_init", "protocolVersion": 3, "userId": "e2e-user", "audioFormat": "audio/pcm;rate=16000"}); err != nil {
		t.Fatal(err)
	}

	readUntilType(t, conn, "examiner_audio_end") // introduction
	wsWriteJSON(t, conn, map[string]any{"type": "ready"})
	for part1 := 0; part1 < 12; part1++ {
		readQuestion(t, conn, 1)
		writeAnswer(t, conn)
	}
	readUntilType(t, conn, "examiner_audio_end") // Part 2 transition
	readUntilType(t, conn, "examiner_audio_end") // cue card wording
	wsWriteJSON(t, conn, map[string]any{"type": "ready"})
	readUntilType(t, conn, "prep_start")
	readUntilType(t, conn, "long_turn_start")
	time.Sleep(7 * time.Millisecond)
	writeAnswer(t, conn)

	readQuestion(t, conn, 2) // rounding-off
	writeAnswer(t, conn)
	for part3 := 0; part3 < 4; part3++ {
		readQuestion(t, conn, 3)
		writeAnswer(t, conn)
	}
	evaluation := readUntilType(t, conn, "evaluation")
	if evaluation["status"] != "completed" || evaluation["overall_band"] != float64(7) {
		t.Fatalf("unexpected evaluation: %#v", evaluation)
	}

	select {
	case saved := <-repo.created:
		if saved.QuestionType != "full_interview" || saved.Transcript == "" {
			t.Fatalf("candidate-only session was not persisted: %#v", saved)
		}
	case <-time.After(time.Second):
		t.Fatal("scored session was not persisted")
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	if len(store.records) != 1 {
		t.Fatalf("got %d interview records", len(store.records))
	}
	for id, record := range store.records {
		if record.Status != "complete" || len(store.turns[id]) != len(record.Snapshot.Transcript.Turns) {
			t.Fatalf("turn/progress persistence drifted: record=%#v turns=%d", record, len(store.turns[id]))
		}
	}
	if generator.calls != 3 || transcriber.calls != 18 || voice.calls == 0 {
		t.Fatalf("unexpected adaptive pipeline calls: generator=%d stt=%d tts=%d", generator.calls, transcriber.calls, voice.calls)
	}
}

func TestInterviewProtocolRefusesV2WithTypedError(t *testing.T) {
	bank, _ := interview.LoadDefaultBank()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		HandleInterviewWebSocket(w, r, InterviewSocketDeps{
			Config: &Config{MaxConnections: 10}, Store: newMemoryInterviewStore(),
			Transcriber: &deterministicTranscriber{}, Voice: &instantVoice{}, Bank: bank,
		})
	}))
	defer server.Close()
	u, _ := url.Parse(server.URL)
	u.Scheme = "ws"
	conn, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	wsWriteJSON(t, conn, map[string]any{"type": "session_init", "protocolVersion": 2, "userId": "old-client", "audioFormat": "audio/webm"})
	frame := readUntilType(t, conn, "error")
	if frame["code"] != "unsupported_protocol" || frame["expected_protocol"] != float64(3) {
		t.Fatalf("unexpected refusal: %#v", frame)
	}
}

func TestInterviewProtocolResumesTheUnansweredTurn(t *testing.T) {
	bank, _ := interview.LoadDefaultBank()
	store := newMemoryInterviewStore()
	deps := InterviewSocketDeps{
		Config: &Config{MaxConnections: 10}, Store: store,
		Transcriber: &deterministicTranscriber{}, Voice: &instantVoice{}, Bank: bank,
		Timing: interview.DefaultTiming(),
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		HandleInterviewWebSocket(w, r, deps)
	}))
	defer server.Close()
	dial := func() *websocket.Conn {
		u, _ := url.Parse(server.URL)
		u.Scheme = "ws"
		conn, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
		if err != nil {
			t.Fatal(err)
		}
		_ = conn.SetReadDeadline(time.Now().Add(5 * time.Second))
		return conn
	}

	first := dial()
	wsWriteJSON(t, first, map[string]any{"type": "session_init", "protocolVersion": 3, "userId": "resume-user", "audioFormat": "audio/pcm;rate=16000"})
	started := readUntilType(t, first, "session_started")
	sessionID, _ := started["session_id"].(string)
	readUntilType(t, first, "examiner_audio_end")
	wsWriteJSON(t, first, map[string]any{"type": "ready"})
	readQuestion(t, first, 1)
	writeAnswer(t, first)
	secondQuestion := readQuestion(t, first, 1)
	_ = first.Close()

	resumed := dial()
	defer resumed.Close()
	wsWriteJSON(t, resumed, map[string]any{
		"type": "session_init", "protocolVersion": 3, "userId": "resume-user",
		"audioFormat": "audio/pcm;rate=16000", "resumeSessionId": sessionID,
	})
	resumedStart := readUntilType(t, resumed, "session_started")
	if resumedStart["resumed"] != true || resumedStart["session_id"] != sessionID {
		t.Fatalf("resume acknowledgement drifted: %#v", resumedStart)
	}
	resumedQuestion := readQuestion(t, resumed, 1)
	if resumedQuestion["question_id"] != secondQuestion["question_id"] || resumedQuestion["turn_id"] != secondQuestion["turn_id"] {
		t.Fatalf("resume changed the unanswered turn: before=%#v after=%#v", secondQuestion, resumedQuestion)
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	if got := store.records[sessionID].Snapshot.Transcript.CandidateText(); got == "" {
		t.Fatal("resume lost the completed first answer")
	}
}

func writeAnswer(t *testing.T, conn *websocket.Conn) {
	t.Helper()
	if err := conn.WriteMessage(websocket.BinaryMessage, []byte{1, 2, 3, 4}); err != nil {
		t.Fatal(err)
	}
	wsWriteJSON(t, conn, map[string]any{"type": "audio_end"})
}

func wsWriteJSON(t *testing.T, conn *websocket.Conn, value any) {
	t.Helper()
	if err := conn.WriteJSON(value); err != nil {
		t.Fatal(err)
	}
}

func readQuestion(t *testing.T, conn *websocket.Conn, part int) map[string]any {
	t.Helper()
	for {
		frame := readNextJSON(t, conn)
		if frame["type"] == "examiner_turn" && frame["part"] == float64(part) && frame["expects_response"] == true {
			turnID := frame["turn_id"]
			for {
				end := readNextJSON(t, conn)
				if end["type"] == "examiner_audio_end" && end["turn_id"] == turnID {
					return frame
				}
			}
		}
	}
}

func readUntilType(t *testing.T, conn *websocket.Conn, typ string) map[string]any {
	t.Helper()
	for {
		frame := readNextJSON(t, conn)
		if frame["type"] == typ {
			return frame
		}
	}
}

func readNextJSON(t *testing.T, conn *websocket.Conn) map[string]any {
	t.Helper()
	for {
		messageType, payload, err := conn.ReadMessage()
		if err != nil {
			t.Fatal(err)
		}
		if messageType == websocket.BinaryMessage {
			continue
		}
		var frame map[string]any
		if err := json.Unmarshal(payload, &frame); err != nil {
			t.Fatal(err)
		}
		return frame
	}
}
