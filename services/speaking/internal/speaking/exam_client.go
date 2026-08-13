package speaking

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/interview"
)

// ExamSessionClient is the service boundary for paid speaking exams. The
// Speaking service owns the live interview; Exam owns the attempt, transcript,
// score, history and progress records.
type ExamSessionClient interface {
	Heartbeat(context.Context, string, string) error
	SubmitPart(context.Context, string, string, ExamTranscriptPart) (map[string]any, error)
	Abandon(context.Context, string, string) error
}

type ExamTranscriptPart struct {
	Part           int                  `json:"part"`
	TranscriptText string               `json:"transcript_text"`
	DurationS      int                  `json:"duration_s"`
	QuestionText   string               `json:"question_text"`
	Words          []ExamTranscriptWord `json:"words,omitempty"`
	AudioDurationS float64              `json:"audio_duration_s,omitempty"`
}

type ExamTranscriptWord struct {
	Word        string  `json:"word"`
	Start       float64 `json:"start"`
	End         float64 `json:"end"`
	Probability float64 `json:"probability,omitempty"`
}

type HTTPExamSessionClient struct {
	baseURL string
	apiKey  string
	client  *http.Client
}

func NewExamSessionClient(baseURL, apiKey string) *HTTPExamSessionClient {
	return &HTTPExamSessionClient{
		baseURL: strings.TrimRight(baseURL, "/"), apiKey: apiKey,
		client: &http.Client{Timeout: 3 * time.Minute},
	}
}

func (c *HTTPExamSessionClient) Heartbeat(ctx context.Context, sessionID, userID string) error {
	return c.do(ctx, http.MethodPatch, "/sessions/"+sessionID+"/heartbeat", userID, nil, nil)
}

func (c *HTTPExamSessionClient) SubmitPart(ctx context.Context, sessionID, userID string, part ExamTranscriptPart) (map[string]any, error) {
	var result map[string]any
	err := c.do(ctx, http.MethodPost, "/internal/sessions/"+sessionID+"/speaking/transcripts", userID, part, &result)
	return result, err
}

func (c *HTTPExamSessionClient) Abandon(ctx context.Context, sessionID, userID string) error {
	return c.do(ctx, http.MethodPost, "/internal/sessions/"+sessionID+"/speaking/abandon", userID, nil, nil)
}

func (c *HTTPExamSessionClient) do(ctx context.Context, method, path, userID string, body any, target any) error {
	var reader io.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(payload)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	if err != nil {
		return err
	}
	req.Header.Set("X-Internal-API-Key", c.apiKey)
	req.Header.Set("X-User-Id", userID)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		message, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("exam service %s returned %d: %s", path, resp.StatusCode, strings.TrimSpace(string(message)))
	}
	if target == nil || resp.StatusCode == http.StatusNoContent {
		return nil
	}
	if err := json.NewDecoder(resp.Body).Decode(target); err != nil {
		return fmt.Errorf("decode exam service response: %w", err)
	}
	return nil
}

func buildExamPart(transcript interview.Transcript, part int) ExamTranscriptPart {
	var questions, answers []string
	words := make([]ExamTranscriptWord, 0)
	var duration float64
	for _, turn := range transcript.Turns {
		if turn.Part != part || strings.TrimSpace(turn.Text) == "" {
			continue
		}
		if turn.Speaker == interview.SpeakerExaminer {
			questions = append(questions, strings.TrimSpace(turn.Text))
			continue
		}
		answers = append(answers, strings.TrimSpace(turn.Text))
		for _, word := range turn.Words {
			words = append(words, ExamTranscriptWord{
				Word: word.Word, Start: duration + word.StartS,
				End: duration + word.EndS, Probability: word.Probability,
			})
		}
		duration += max(0, turn.EndS-turn.StartS)
	}
	return ExamTranscriptPart{
		Part: part, TranscriptText: strings.Join(answers, "\n"),
		DurationS: int(duration + .5), QuestionText: strings.Join(questions, "\n"),
		Words: words, AudioDurationS: duration,
	}
}
