package speaking

import (
	"encoding/json"
	"net/http"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// SPEAK-EVAL-002 — the explicit end-of-audio frame.
//
// Completion used to be decided only by 1.5s of silence. That timer cannot tell
// "the user finished" from "the client stalled", and it charged every session
// 1.5s of latency to find out. `audio_end` is now the normal path; the timer
// remains as the fallback for a client that vanishes mid-recording.
//
// The risk this file covers is double transcription: an explicit frame racing
// the fallback timer, or a duplicate frame from a retrying client, must not
// score the same utterance twice.

// TestAudioEndTriggersTranscriptionWithoutWaitingForVAD proves the latency win:
// the transcript arrives well inside the 1.5s the silence timer would have cost.
func TestAudioEndTriggersTranscriptionWithoutWaitingForVAD(t *testing.T) {
	s := newSpeakingTestServer(t, &mockLLMClient{}, &mockTTSClient{})
	ws := openSessionWithoutAudio(t, s)

	if err := ws.WriteMessage(websocket.BinaryMessage, make([]byte, 3200)); err != nil {
		t.Fatalf("audio: %v", err)
	}

	started := time.Now()
	if err := ws.WriteMessage(websocket.TextMessage, []byte(`{"type":"audio_end"}`)); err != nil {
		t.Fatalf("audio_end: %v", err)
	}

	frame := readFrameOfType(t, ws, "transcript", 5*time.Second)
	elapsed := time.Since(started)

	if frame == nil {
		t.Fatal("no transcript frame after audio_end")
	}
	if elapsed >= 1500*time.Millisecond {
		t.Errorf(
			"transcript took %v after audio_end; the point of the frame is not to "+
				"wait out the 1.5s VAD window",
			elapsed,
		)
	}
}

// TestDuplicateAudioEndTranscribesOnce — a retrying or buggy client must not
// cause the same utterance to be scored twice, which would double the LLM spend
// and could deliver two contradictory evaluations for one answer.
func TestDuplicateAudioEndTranscribesOnce(t *testing.T) {
	s := newSpeakingTestServer(t, &mockLLMClient{}, &mockTTSClient{})
	ws := openSessionWithoutAudio(t, s)

	if err := ws.WriteMessage(websocket.BinaryMessage, make([]byte, 3200)); err != nil {
		t.Fatalf("audio: %v", err)
	}
	for i := 0; i < 3; i++ {
		if err := ws.WriteMessage(websocket.TextMessage, []byte(`{"type":"audio_end"}`)); err != nil {
			t.Fatalf("audio_end %d: %v", i, err)
		}
	}

	if frame := readFrameOfType(t, ws, "transcript", 5*time.Second); frame == nil {
		t.Fatal("no transcript frame at all")
	}

	// A second transcript would mean the buffer was drained twice. The buffer is
	// reset under the mutex inside triggerTranscription, so the second and third
	// frames find it empty and return.
	if extra := readFrameOfType(t, ws, "transcript", 1200*time.Millisecond); extra != nil {
		t.Errorf("a duplicate audio_end produced a second transcript: %v", extra)
	}
}

// TestAudioEndAfterVADIsHarmless — the reverse race: the fallback timer fires
// first (slow client), then audio_end arrives.
func TestAudioEndAfterVADIsHarmless(t *testing.T) {
	s := newSpeakingTestServer(t, &mockLLMClient{}, &mockTTSClient{})
	ws := openSessionWithoutAudio(t, s)

	if err := ws.WriteMessage(websocket.BinaryMessage, make([]byte, 3200)); err != nil {
		t.Fatalf("audio: %v", err)
	}

	// Let the VAD window elapse and transcription fire on its own.
	if frame := readFrameOfType(t, ws, "transcript", 6*time.Second); frame == nil {
		t.Fatal("VAD fallback did not transcribe")
	}

	if err := ws.WriteMessage(websocket.TextMessage, []byte(`{"type":"audio_end"}`)); err != nil {
		t.Fatalf("late audio_end: %v", err)
	}
	if extra := readFrameOfType(t, ws, "transcript", 1200*time.Millisecond); extra != nil {
		t.Errorf("audio_end after the VAD fallback produced a second transcript: %v", extra)
	}
}

// TestAudioEndWithNoAudioIsIgnored — pressing stop before speaking must not
// produce a transcript, an evaluation, or a band.
func TestAudioEndWithNoAudioIsIgnored(t *testing.T) {
	s := newSpeakingTestServer(t, &mockLLMClient{}, &mockTTSClient{})
	ws := openSessionWithoutAudio(t, s)

	if err := ws.WriteMessage(websocket.TextMessage, []byte(`{"type":"audio_end"}`)); err != nil {
		t.Fatalf("audio_end: %v", err)
	}

	if frame := readFrameOfType(t, ws, "transcript", 1500*time.Millisecond); frame != nil {
		t.Errorf("audio_end with an empty buffer produced a transcript: %v", frame)
	}
}

// TestUnknownControlFrameDoesNotDropTheSession — a future protocol version may
// add frames this build predates. Closing the socket for an unknown one would
// make the protocol impossible to extend without lockstep deploys.
func TestUnknownControlFrameDoesNotDropTheSession(t *testing.T) {
	s := newSpeakingTestServer(t, &mockLLMClient{}, &mockTTSClient{})
	ws := openSessionWithoutAudio(t, s)

	if err := ws.WriteMessage(websocket.TextMessage, []byte(`{"type":"some_future_frame"}`)); err != nil {
		t.Fatalf("unknown frame: %v", err)
	}
	if err := ws.WriteMessage(websocket.BinaryMessage, make([]byte, 3200)); err != nil {
		t.Fatalf("audio after unknown frame: %v", err)
	}
	if err := ws.WriteMessage(websocket.TextMessage, []byte(`{"type":"audio_end"}`)); err != nil {
		t.Fatalf("audio_end: %v", err)
	}

	if frame := readFrameOfType(t, ws, "transcript", 5*time.Second); frame == nil {
		t.Fatal("session did not survive an unknown control frame")
	}
}

// --- session_init rejection ------------------------------------------------

func TestSessionInitWithoutAudioFormatIsRejected(t *testing.T) {
	s := newSpeakingTestServer(t, &mockLLMClient{}, &mockTTSClient{})
	ws := dialSpeaking(t, s)

	init, _ := json.Marshal(map[string]string{
		"type": "session_init", "userId": "user-1",
		"questionPrompt": "Describe a book.", "questionType": "IELTS Part 2",
		// No audioFormat: a pre-SPEAK-EVAL-002 client.
	})
	if err := ws.WriteMessage(websocket.TextMessage, init); err != nil {
		t.Fatalf("session_init: %v", err)
	}

	frame := readFrameOfType(t, ws, "error", 3*time.Second)
	if frame == nil {
		t.Fatal("a session that declared no audio format was accepted")
	}
	message, _ := frame["message"].(string)
	if message == "" {
		t.Error("rejection carried no message for the user")
	}
}

func TestSessionInitWithUnsupportedAudioFormatIsRejected(t *testing.T) {
	s := newSpeakingTestServer(t, &mockLLMClient{}, &mockTTSClient{})
	ws := dialSpeaking(t, s)

	init, _ := json.Marshal(map[string]string{
		"type": "session_init", "userId": "user-1",
		"questionPrompt": "Describe a book.", "questionType": "IELTS Part 2",
		"audioFormat": "audio/flac",
	})
	if err := ws.WriteMessage(websocket.TextMessage, init); err != nil {
		t.Fatalf("session_init: %v", err)
	}

	if frame := readFrameOfType(t, ws, "error", 3*time.Second); frame == nil {
		t.Fatal("an unsupported audio format was accepted")
	}
}

// --- helpers ---------------------------------------------------------------

func dialSpeaking(t *testing.T, s *speakingTestServer) *websocket.Conn {
	t.Helper()
	ws, _, err := websocket.DefaultDialer.Dial(s.url, http.Header{})
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	t.Cleanup(func() { ws.Close() })
	return ws
}

// openSessionWithoutAudio dials and initialises but sends no audio, so a test
// controls exactly when the utterance ends.
func openSessionWithoutAudio(t *testing.T, s *speakingTestServer) *websocket.Conn {
	t.Helper()
	ws := dialSpeaking(t, s)

	init, _ := json.Marshal(map[string]string{
		"type": "session_init", "userId": "user-1",
		"questionPrompt": "Describe a book.", "questionType": "IELTS Part 2",
		"audioFormat": "audio/pcm;rate=16000",
	})
	if err := ws.WriteMessage(websocket.TextMessage, init); err != nil {
		t.Fatalf("session_init: %v", err)
	}
	return ws
}

// readFrameOfType drains frames until one matches, or the budget expires.
// Returns nil on timeout rather than failing, so a caller can assert either that
// a frame arrives or that none does.
func readFrameOfType(t *testing.T, ws *websocket.Conn, want string, within time.Duration) map[string]any {
	t.Helper()
	deadline := time.Now().Add(within)
	for {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			return nil
		}
		if err := ws.SetReadDeadline(time.Now().Add(remaining)); err != nil {
			return nil
		}
		msgType, payload, err := ws.ReadMessage()
		if err != nil {
			return nil
		}
		if msgType != websocket.TextMessage {
			continue
		}
		var frame map[string]any
		if err := json.Unmarshal(payload, &frame); err != nil {
			continue
		}
		if frame["type"] == want {
			return frame
		}
	}
}
