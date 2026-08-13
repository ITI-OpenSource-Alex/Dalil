package speaking

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"

	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/agents"
	"github.com/ITI-OpenSource-Alex/GOA/services/speaking/internal/interview"
)

type TurnTranscription struct {
	Text      string
	DurationS float64
	Words     []interview.WordTiming
}

type TurnTranscriber interface {
	TranscribeTurn(context.Context, []byte, string) (TurnTranscription, error)
}

type SpeechTurnTranscriber struct{ speechURL string }

func NewSpeechTurnTranscriber(speechURL string) *SpeechTurnTranscriber {
	return &SpeechTurnTranscriber{speechURL: speechURL}
}

func (t *SpeechTurnTranscriber) TranscribeTurn(ctx context.Context, audio []byte, declaredFormat string) (TurnTranscription, error) {
	if t.speechURL == "" {
		return TurnTranscription{}, fmt.Errorf("speech service URL is not configured")
	}
	format, ok := lookupAudioFormat(declaredFormat)
	if !ok {
		return TurnTranscription{}, fmt.Errorf("unsupported audio format %q", declaredFormat)
	}
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	header := make(textproto.MIMEHeader)
	header.Set("Content-Disposition", fmt.Sprintf(`form-data; name="audio"; filename="audio%s"`, format.extension))
	header.Set("Content-Type", format.uploadContentType)
	part, err := writer.CreatePart(header)
	if err != nil {
		return TurnTranscription{}, err
	}
	if _, err := part.Write(audio); err != nil {
		return TurnTranscription{}, err
	}
	if err := writer.Close(); err != nil {
		return TurnTranscription{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, t.speechURL+"/stt", body)
	if err != nil {
		return TurnTranscription{}, err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	resp, err := httpClient.Do(req)
	if err != nil {
		return TurnTranscription{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		message, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return TurnTranscription{}, fmt.Errorf("speech service returned %d: %s", resp.StatusCode, string(message))
	}
	var payload struct {
		Transcript string        `json:"transcript"`
		DurationS  float64       `json:"duration_s"`
		Words      []agents.Word `json:"words"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return TurnTranscription{}, err
	}
	words := make([]interview.WordTiming, 0, len(payload.Words))
	for _, word := range payload.Words {
		words = append(words, interview.WordTiming{
			Word: word.Word, StartS: word.Start, EndS: word.End, Probability: word.Probability,
		})
	}
	return TurnTranscription{Text: payload.Transcript, DurationS: payload.DurationS, Words: words}, nil
}
