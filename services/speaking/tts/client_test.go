package tts

import (
	"context"
	"strings"
	"testing"
)

func TestTTSUnavailableWhenSidecarDown(t *testing.T) {
	// Point to a non-existent port on localhost to simulate a downed sidecar
	client := NewClient("http://localhost:59999")

	err := client.StreamTTS(context.Background(), "Hello", func(chunk []byte) error {
		return nil
	})

	if err == nil {
		t.Fatal("Expected an error when the sidecar is down, but got nil")
	}

	if !strings.Contains(err.Error(), "connection refused") && !strings.Contains(err.Error(), "connect: cannot assign requested address") && !strings.Contains(err.Error(), "TTS HTTP request connection failed") {
		t.Errorf("Expected a connection refused/failed error, got: %v", err)
	}
}
