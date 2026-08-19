package speaking

import (
	"bytes"
	"context"
	"errors"
	"sync"
)

var errTTSUnavailable = errors.New("examiner TTS is unavailable")

type VoicePrompt struct {
	Key  string
	Text string
}

const defaultExaminerVoiceID = "piper/en_US-lessac-medium"

type ExaminerVoice interface {
	VoiceID() string
	Audio(context.Context, string, string) ([]byte, error)
}

type cachedVoiceEntry struct {
	done  chan struct{}
	audio []byte
	err   error
}

// CachedExaminerVoice collapses concurrent synthesis and retains fixed bank
// audio by question id. Generated follow-ups are content-hashed by their stable
// generated question id and receive the same treatment on replay/resume.
type CachedExaminerVoice struct {
	tts     TTSClient
	voiceID string
	mu      sync.Mutex
	entries map[string]*cachedVoiceEntry
}

func NewCachedExaminerVoice(tts TTSClient) *CachedExaminerVoice {
	return &CachedExaminerVoice{
		tts: tts, voiceID: defaultExaminerVoiceID,
		entries: make(map[string]*cachedVoiceEntry),
	}
}

func (v *CachedExaminerVoice) VoiceID() string { return v.voiceID }

func (v *CachedExaminerVoice) Audio(ctx context.Context, key, text string) ([]byte, error) {
	if v == nil || v.tts == nil {
		return nil, errTTSUnavailable
	}
	v.mu.Lock()
	if existing, ok := v.entries[key]; ok {
		v.mu.Unlock()
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-existing.done:
			return append([]byte(nil), existing.audio...), existing.err
		}
	}
	entry := &cachedVoiceEntry{done: make(chan struct{})}
	v.entries[key] = entry
	v.mu.Unlock()

	var audio bytes.Buffer
	entry.err = v.tts.StreamTTS(ctx, text, func(chunk []byte) error {
		_, err := audio.Write(chunk)
		return err
	})
	if entry.err == nil {
		entry.audio = append([]byte(nil), audio.Bytes()...)
	} else {
		// Do not permanently poison a prompt after a transient sidecar failure.
		v.mu.Lock()
		if v.entries[key] == entry {
			delete(v.entries, key)
		}
		v.mu.Unlock()
	}
	close(entry.done)
	return append([]byte(nil), entry.audio...), entry.err
}

func (v *CachedExaminerVoice) Prewarm(ctx context.Context, prompts []VoicePrompt) {
	for _, prompt := range prompts {
		if ctx.Err() != nil {
			return
		}
		_, _ = v.Audio(ctx, prompt.Key, prompt.Text)
	}
}
