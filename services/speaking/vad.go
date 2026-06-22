package main

import (
	"time"

	"github.com/rs/zerolog/log"
)

func (c *Client) vadTicker() {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-c.ctx.Done():
			return
		case <-ticker.C:
			c.bufferMutex.Lock()
			lastAudio := c.lastAudioAt
			var bufLen int
			if c.audioBuffer != nil {
				bufLen = c.audioBuffer.Len()
			}
			c.bufferMutex.Unlock()

			if bufLen > 0 && time.Since(lastAudio) > 1500*time.Millisecond {
				log.Info().Str("session_id", c.id).Msg("Silence detected, triggering transcription")
				c.triggerTranscription()
			}
		}
	}
}

func (c *Client) triggerTranscription() {
	c.bufferMutex.Lock()
	if c.audioBuffer == nil || c.audioBuffer.Len() == 0 {
		c.bufferMutex.Unlock()
		return
	}

	audioBytes := make([]byte, c.audioBuffer.Len())
	copy(audioBytes, c.audioBuffer.Bytes())
	c.audioBuffer.Reset()
	c.bufferMutex.Unlock()

	go c.transcribeFn(audioBytes)
}
