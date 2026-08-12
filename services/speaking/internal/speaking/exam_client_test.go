package speaking

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/interview"
)

func TestBuildExamPartPreservesStructureAndOffsetsWords(t *testing.T) {
	part := buildExamPart(interview.Transcript{Turns: []interview.Turn{
		{Part: 1, Speaker: interview.SpeakerExaminer, Text: "Where do you live?"},
		{Part: 1, Speaker: interview.SpeakerCandidate, Text: "In Alexandria.", EndS: 2, Words: []interview.WordTiming{{Word: "In", StartS: 0, EndS: .2}}},
		{Part: 1, Speaker: interview.SpeakerExaminer, Text: "What do you like?"},
		{Part: 1, Speaker: interview.SpeakerCandidate, Text: "The sea.", StartS: 2, EndS: 5, Words: []interview.WordTiming{{Word: "The", StartS: 0, EndS: .3}}},
		{Part: 2, Speaker: interview.SpeakerCandidate, Text: "Not part one", EndS: 9},
	}}, 1)
	if part.TranscriptText != "In Alexandria.\nThe sea." || part.QuestionText != "Where do you live?\nWhat do you like?" {
		t.Fatalf("part structure was lost: %#v", part)
	}
	if part.DurationS != 5 || len(part.Words) != 2 || part.Words[1].Start != 2 {
		t.Fatalf("part timing was not normalized: %#v", part)
	}
}

func TestExamClientSendsServerCredentialsAndUser(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-API-Key") != "key" || r.Header.Get("X-User-Id") != "user-1" {
			t.Errorf("missing trusted headers: %#v", r.Header)
		}
		var part ExamTranscriptPart
		if err := json.NewDecoder(r.Body).Decode(&part); err != nil || part.Part != 3 {
			t.Errorf("bad part payload: %#v, %v", part, err)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"completed","overall_band":7.5}`))
	}))
	defer server.Close()

	client := NewExamSessionClient(server.URL, "key")
	result, err := client.SubmitPart(context.Background(), "session-1", "user-1", ExamTranscriptPart{Part: 3})
	if err != nil || result["status"] != "completed" {
		t.Fatalf("SubmitPart failed: result=%#v err=%v", result, err)
	}
}
