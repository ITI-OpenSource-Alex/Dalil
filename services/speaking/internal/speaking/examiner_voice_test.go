package speaking

import (
	"context"
	"sync"
	"testing"
	"time"
)

type countingTTS struct {
	mu    sync.Mutex
	calls int
}

func (t *countingTTS) StreamTTS(_ context.Context, text string, write func([]byte) error) error {
	t.mu.Lock()
	t.calls++
	t.mu.Unlock()
	time.Sleep(5 * time.Millisecond)
	return write([]byte("wav:" + text))
}

func TestCachedExaminerVoiceSynthesizesOneCopyPerQuestion(t *testing.T) {
	provider := &countingTTS{}
	voice := NewCachedExaminerVoice(provider)
	var wait sync.WaitGroup
	for range 8 {
		wait.Add(1)
		go func() {
			defer wait.Done()
			audio, err := voice.Audio(context.Background(), "p1.home.q1", "Where do you live?")
			if err != nil || string(audio) != "wav:Where do you live?" {
				t.Errorf("audio=%q err=%v", audio, err)
			}
		}()
	}
	wait.Wait()
	provider.mu.Lock()
	defer provider.mu.Unlock()
	if provider.calls != 1 {
		t.Fatalf("fixed question was synthesized %d times, want 1", provider.calls)
	}
}
