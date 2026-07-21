export class AudioPlayer {
  private chunks: Uint8Array[] = [];

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
}
