import { useEffect, useRef, useState } from "react";

const FFT_SIZE = 2048;

type AudioContextConstructor = typeof AudioContext;

function getAudioContextConstructor(): AudioContextConstructor | null {
  if (typeof window === "undefined") return null;

  return (
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: AudioContextConstructor })
      .webkitAudioContext ??
    null
  );
}

/**
 * Owns the Web Audio graph (AudioContext + AnalyserNode) for a live
 * MediaStream. It never connects the analyser to the audio destination, so
 * it only reads audio data — it never plays it back or causes feedback.
 *
 * The stream itself is *not* owned here: track cleanup (stopping the mic)
 * stays the sole responsibility of whoever acquired it (AudioRecorder), so
 * this hook only tears down its own graph/context on stream change/unmount.
 */
export function useAudioVisualizer(stream: MediaStream | null) {
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [isSupported] = useState(() => getAudioContextConstructor() !== null);

  const audioContextRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    if (!stream || !isSupported) {
      setAnalyser(null);
      return;
    }

    const AudioContextCtor = getAudioContextConstructor();
    if (!AudioContextCtor) {
      setAnalyser(null);
      return;
    }

    let audioContext: AudioContext;
    let source: MediaStreamAudioSourceNode;
    let analyserNode: AnalyserNode;

    try {
      audioContext = new AudioContextCtor();
      source = audioContext.createMediaStreamSource(stream);
      analyserNode = audioContext.createAnalyser();
      analyserNode.fftSize = FFT_SIZE;

      // Read-only tap: analyser is never connected to destination.
      source.connect(analyserNode);

      if (audioContext.state === "suspended") {
        // Safari/iOS may start contexts suspended even after a user
        // gesture triggered the recording; resume defensively.
        void audioContext.resume();
      }
    } catch (err) {
      console.error(
        "useAudioVisualizer: failed to initialize Web Audio graph",
        err,
      );
      setAnalyser(null);
      return;
    }

    audioContextRef.current = audioContext;
    setAnalyser(analyserNode);

    return () => {
      source.disconnect();
      analyserNode.disconnect();
      audioContextRef.current = null;

      if (audioContext.state !== "closed") {
        void audioContext.close();
      }

      setAnalyser(null);
    };
  }, [stream, isSupported]);

  return { analyser, isSupported };
}
