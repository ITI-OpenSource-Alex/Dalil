export class AudioPlayer {
  private chunks: Uint8Array[] = [];
  private currentAudio: HTMLAudioElement | null = null;
  private currentUrl: string | null = null;
  private currentResolve: (() => void) | null = null;
  private playbackChain: Promise<void> = Promise.resolve();

  addChunk(chunk: ArrayBuffer) {
    this.chunks.push(new Uint8Array(chunk));
  }

  async play() {
    if (this.chunks.length === 0) return;

    const blob = new Blob(this.chunks as BlobPart[], {
      type: "audio/mpeg",
    });

    const url = URL.createObjectURL(blob);

    const audio = new Audio(url);

    await audio.play();

    audio.onended = () => {
      URL.revokeObjectURL(url);
    };

    this.chunks = [];
  }

  async playExaminerTurn(buffer: ArrayBuffer): Promise<void> {
    this.stop();
    const blob = new Blob([buffer], { type: "audio/wav" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    this.currentAudio = audio;
    this.currentUrl = url;

    await new Promise<void>((resolve, reject) => {
      this.currentResolve = resolve;
      audio.onended = () => {
        this.releaseCurrent();
        resolve();
      };
      audio.onerror = () => {
        this.releaseCurrent();
        reject(new Error("Examiner audio could not be played."));
      };
      audio.play().catch((error) => {
        this.releaseCurrent();
        reject(error);
      });
    });
  }

  queueExaminerTurn(buffer: ArrayBuffer): Promise<void> {
    const playback = this.playbackChain.then(() => this.playExaminerTurn(buffer));
    this.playbackChain = playback.catch(() => undefined);
    return playback;
  }

  stop() {
    const resolve = this.currentResolve;
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
    }
    this.releaseCurrent();
    resolve?.();
  }

  private releaseCurrent() {
    if (this.currentUrl) URL.revokeObjectURL(this.currentUrl);
    this.currentAudio = null;
    this.currentUrl = null;
    this.currentResolve = null;
  }
}
