# Speaking Service

The Speaking service is a Go service designed for real-time speaking practice. It handles long-lived WebSocket connections, enforces client capacity limits, parses streaming audio streams, applies Voice Activity Detection (VAD) to find periods of silence, and connects to ElevenLabs for speech-to-text transcription.

---

## What it Owns

* **Responsibility**: Bidirectional audio streaming over WebSockets, VAD silence checks (1.5 seconds silence threshold), and ElevenLabs STT.
* **Database**: N/A (Stateless service).
* **Queues**: N/A.

---

## API Reference

### 1. `GET /ws` (WebSocket Handshake)
* **Auth Required**: Yes (Gateway forwards JWT in query parameters or headers)
* **Protocol**: Upgrade HTTP connection to RFC 6455 WebSockets.
* **WebSocket Message Types**:
  * **Client Inbound Message**: Binary audio chunks (linear PCM 16kHz mono).
  * **Server Outbound Message**: Text frames containing real-time transcripts.
    ```json
    {
      "type": "transcript",
      "text": "Hello, I would like to register.",
      "isFinal": true
    }
    ```
* **Error Handshake Codes**:
  * `400 Bad Request`: Incorrect headers or malformed Base64 handshake key.
  * `503 Service Unavailable`: Connection capacity full (exceeded `MAX_CONNECTIONS`).

### 2. `GET /metrics`
* **Response Shape (200 OK)**:
```text
# HELP goa_speaking_active_connections Number of active connections
# TYPE goa_speaking_active_connections gauge
goa_speaking_active_connections 2
```

---

## Environment Variables

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `PORT` | Go server port binding. | `8082` |
| `MAX_CONNECTIONS` | Max active simultaneous WebSocket sessions allowed. | `100` |
| `ELEVENLABS_API_KEY`| ElevenLabs authorization credential. | `mock-key` |
| `OTEL_SERVICE_NAME` | OpenTelemetry tracing identity name. | `speaking` |

---

## How to Run Locally

### Running outside Docker
```bash
go run main.go
# Or if package structure has cmd/speaking
go run cmd/speaking/main.go
```

### Running with Docker
```bash
docker compose up -d speaking
```

---

## How to Run Tests

```bash
# Run unit and integration tests
go test ./...
```
