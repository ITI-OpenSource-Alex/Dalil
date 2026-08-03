export interface AudioRecorderOptions {
  onAudioChunk: (chunk: ArrayBuffer) => void;
}

export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;

  constructor(private options: AudioRecorderOptions) {}

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
    });

    this.mediaRecorder = new MediaRecorder(this.stream);

    this.mediaRecorder.ondataavailable = async (event) => {
      if (!event.data.size) return;

      const buffer = await event.data.arrayBuffer();

      this.options.onAudioChunk(buffer);
    };

    // Send chunks every 250ms
    this.mediaRecorder.start(250);
  }

  stop() {
    this.mediaRecorder?.stop();

    this.stream?.getTracks().forEach((track) => track.stop());

    this.mediaRecorder = null;
    this.stream = null;
  }

  /**
   * Exposes the live MediaStream so other consumers (e.g. a waveform
   * visualizer) can tap the same microphone stream instead of requesting
   * getUserMedia a second time. Returns null before start() resolves or
   * after stop() has released the stream.
   */
  getStream(): MediaStream | null {
    return this.stream;
  }
}
