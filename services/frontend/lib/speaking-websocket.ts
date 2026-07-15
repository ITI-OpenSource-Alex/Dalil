export type SocketSpeakingState =
  | "idle"
  | "connecting"
  | "connected"
  | "recording"
  | "processing"
  | "done"
  | "error";

export interface SpeakingEvaluation {
  overall_band: number;
  dimensions: Record<string, any>;
  overall_feedback: string;
  partial?: boolean;
  status?: string;
}

interface SpeakingSessionOptions {
  wsUrl: string;
  userId: string;
  questionPrompt: string;
  questionType: string;

  onStateChange?: (state: SocketSpeakingState) => void;
  onEvaluation?: (evaluation: SpeakingEvaluation) => void;
  onError?: (message: string) => void;
  onTtsChunk?: (audio: ArrayBuffer) => void;
  onTranscript?: (text: string, isFinal: boolean) => void;
}

export class SpeakingWebSocket {
  private socket: WebSocket | null = null;

  constructor(private options: SpeakingSessionOptions) {}

  connect() {
    this.options.onStateChange?.("connecting");

    this.socket = new WebSocket(this.options.wsUrl);
    this.socket.binaryType = "arraybuffer";

    this.socket.onopen = () => {
      this.options.onStateChange?.("connected");

      this.socket?.send(
        JSON.stringify({
          type: "session_init",
          userId: this.options.userId,
          questionPrompt: this.options.questionPrompt,
          questionType: this.options.questionType,
        }),
      );

      this.options.onStateChange?.("recording");
    };

    this.socket.onmessage = async (event) => {
      // Binary = ElevenLabs audio
      if (event.data instanceof Blob) {
        const buffer = await event.data.arrayBuffer();

        this.options.onTtsChunk?.(buffer);

        return;
      }

      const data = JSON.parse(event.data);

      switch (data.type) {
        case "transcript":
          this.options.onTranscript?.(data.text, data.isFinal ?? false);
          break;

        case "evaluation":
          this.options.onEvaluation?.(data);
          break;

        case "error":
          this.options.onError?.(data.message);
          break;
      }
    };

    this.socket.onerror = () => {
      this.options.onStateChange?.("error");
      this.options.onError?.("WebSocket connection failed.");
    };

    this.socket.onclose = () => {
      console.log("Speaking session closed.");
    };
  }

  /**
   * Sends one audio chunk to the backend.
   * Backend expects binary PCM frames.
   */
  sendAudio(chunk: ArrayBuffer | Blob) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    this.socket.send(chunk);
  }

  /**
   * User finished speaking.
   * Stop recording but leave the socket open until
   * the backend returns the evaluation.
   */
  finishRecording() {
    this.options.onStateChange?.("processing");
  }

  close() {
    this.socket?.close();
    this.socket = null;
    this.options.onStateChange?.("idle");
  }
}
