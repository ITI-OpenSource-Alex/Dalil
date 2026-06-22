package speaking

import (
	"bytes"
	"context"
	"sync"
	"testing"
	"time"
)

func TestAudioBufferAccumulation(t *testing.T) {
	buf := &bytes.Buffer{}
	client := &Client{
		audioBuffer: buf,
	}

	chunk1 := []byte{1, 2, 3}
	chunk2 := []byte{4, 5, 6}

	client.audioBuffer.Write(chunk1)
	client.audioBuffer.Write(chunk2)

	expected := []byte{1, 2, 3, 4, 5, 6}
	if !bytes.Equal(client.audioBuffer.Bytes(), expected) {
		t.Errorf("Expected buffer content %v, got %v", expected, client.audioBuffer.Bytes())
	}
}

func TestVADSilenceDetection(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	var transcriptionTriggered bool
	var triggerMutex sync.Mutex
	var receivedAudio []byte

	buf := bytes.NewBuffer(make([]byte, 0, 1024))
	client := &Client{
		id:          "test-session",
		audioBuffer: buf,
		lastAudioAt: time.Now(),
		ctx:         ctx,
		cancel:      cancel,
		transcribeFn: func(audio []byte) {
			triggerMutex.Lock()
			transcriptionTriggered = true
			receivedAudio = audio
			triggerMutex.Unlock()
		},
	}

	// Start VAD ticker in the background
	go client.vadTicker()

	// Write mock audio chunk and update lastAudioAt
	client.bufferMutex.Lock()
	client.audioBuffer.Write([]byte{1, 1, 1})
	client.lastAudioAt = time.Now()
	client.bufferMutex.Unlock()

	// Sleep 1000ms. Since silence threshold is 1500ms, VAD should NOT have fired yet.
	time.Sleep(1000 * time.Millisecond)

	triggerMutex.Lock()
	firedEarly := transcriptionTriggered
	triggerMutex.Unlock()

	if firedEarly {
		t.Fatal("VAD fired too early (before 1500ms of silence)")
	}

	// Sleep another 600ms (total silence = 1600ms). VAD should have fired now.
	time.Sleep(600 * time.Millisecond)

	triggerMutex.Lock()
	firedLate := transcriptionTriggered
	audioResult := receivedAudio
	triggerMutex.Unlock()

	if !firedLate {
		t.Fatal("VAD failed to fire after 1500ms of silence")
	}

	expectedAudio := []byte{1, 1, 1}
	if !bytes.Equal(audioResult, expectedAudio) {
		t.Errorf("Expected transcribed audio %v, got %v", expectedAudio, audioResult)
	}

	// Verify buffer was reset
	client.bufferMutex.Lock()
	bufLen := client.audioBuffer.Len()
	client.bufferMutex.Unlock()

	if bufLen != 0 {
		t.Errorf("Expected audio buffer to be reset to 0, got len %d", bufLen)
	}
}
