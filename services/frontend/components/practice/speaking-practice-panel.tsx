"use client";

import { useEffect, useRef, useState } from "react";
import SpeakingSessionPanel, {
  SpeakingState,
} from "@/components/chat/speaking-session-panel";
import EvaluationBreakdown from "@/components/speaking/evaluation-breakdown";
import {
  AudioRecorder,
  selectRecordingMimeType,
} from "@/lib/audio-recorder";
import {
  SpeakingWebSocket,
  SpeakingEvaluation,
} from "@/lib/speaking-websocket";
import { AudioPlayer } from "@/lib/audio-player";
import { SpeakingDimensions } from "@/app/types/speaking";
import { extractCriteriaScores } from "@/lib/speaking-format";
import { CURRENT_USER_ID } from "@/lib/current-user";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";

// Same derivation as chat-shell.tsx: http -> ws, https -> wss, so the two
// cannot drift apart.
const SPEAKING_WS_URL =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080").replace(
    /^http/,
    "ws",
  ) + "/api/speaking/ws";

/**
 * Speaking Practice, standalone. Extracted from chat-shell.tsx's speaking
 * machinery (the WebSocket lifecycle, recorder wiring, state machine) with
 * one behavioural change: on completion, the evaluation renders directly on
 * this page via EvaluationBreakdown (the same component the session-history
 * detail page and the public share page use) instead of being appended to a
 * chat transcript -- there is no transcript here to append to, and a
 * dedicated practice page is a better home for the result than a chat
 * bubble was.
 *
 * Session persistence is unchanged: the Speaking service writes the
 * completed session to speaking_sessions server-side once evaluation
 * finishes, the same way it already did for chat-triggered sessions. This
 * component doesn't need to (and doesn't) do anything extra for the result
 * to show up in Speaking History afterwards.
 */
export default function SpeakingPracticePanel() {
  const speakingSocket = useRef<SpeakingWebSocket | null>(null);
  const audioPlayer = useRef(new AudioPlayer());
  const recorderRef = useRef<AudioRecorder | null>(null);
  const transcriptionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  const [state, setState] = useState<SpeakingState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState("");
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [sessionKey, setSessionKey] = useState(0);
  const [evaluation, setEvaluation] = useState<SpeakingEvaluation | null>(null);

  const { user } = useCurrentUser();
  const userId = user?.id ?? CURRENT_USER_ID;

  // Fixed for now, same prompt chat-shell.tsx used -- a question bank is out
  // of scope here (Reading/Listening Practice have the same gap; see
  // docs/IA-REDESIGN-PROPOSAL.md).
  const speakingQuestion = {
    prompt: "Describe a memorable journey you have taken.",
    type: "part2",
  };

  const clearTranscriptionTimeout = () => {
    if (transcriptionTimeoutRef.current) {
      clearTimeout(transcriptionTimeoutRef.current);
      transcriptionTimeoutRef.current = null;
    }
  };

  const openSocket = () => {
    setSessionKey((key) => key + 1);
    clearTranscriptionTimeout();
    speakingSocket.current?.close();

    // SPEAK-EVAL-002: session_init must declare the recorded audio format.
    //
    // The browser records with MediaRecorder, which emits an encoded container
    // (WebM/Opus on Chrome, Ogg/Opus on Firefox, MP4/AAC on Safari). The backend
    // used to label every upload "audio/pcm;rate=16000", and the speech sidecar
    // decodes anything matching audio/pcm as raw int16 samples -- so the audio
    // arrived as noise and the transcript came back empty.
    //
    // The format is resolved here, before the socket exists, because
    // session_init is sent the instant it opens. selectRecordingMimeType is pure
    // and needs no microphone, so this cannot fail for permission reasons.
    let audioFormat: string;
    try {
      audioFormat = selectRecordingMimeType();
    } catch (err) {
      console.error("No supported recording format:", err);
      setError(
        err instanceof Error
          ? err.message
          : "This browser cannot record audio we can transcribe.",
      );
      setState("idle");
      return;
    }

    speakingSocket.current = new SpeakingWebSocket({
      wsUrl: SPEAKING_WS_URL,
      userId,
      questionPrompt: speakingQuestion.prompt,
      questionType: speakingQuestion.type,
      audioFormat,

      onTranscript: (text) => setTranscript(text),

      onTtsChunk: (audio) => audioPlayer.current.addChunk(audio),

      onError: (message) => {
        console.error("Speaking socket error:", message);
        clearTranscriptionTimeout();
        setError(message);
        setState("idle");
        setAudioStream(null);
      },

      onStateChange: (socketState) => {
        switch (socketState) {
          case "connecting":
            setState("connecting");
            break;

          case "connected":
            setState("listening");

            recorderRef.current = new AudioRecorder({
              onAudioChunk: (chunk) => speakingSocket.current?.sendAudio(chunk),
            });

            recorderRef.current
              .start()
              .then(() => {
                setAudioStream(recorderRef.current?.getStream() ?? null);

                // The browser may normalise the requested type. If what it
                // actually produces differs from what session_init declared, the
                // upload would be mislabelled -- the exact defect SPEAK-EVAL-002
                // removes -- so fail loudly rather than transcribe bytes under
                // the wrong name.
                const actual = recorderRef.current?.getMimeType();
                if (
                  actual &&
                  actual.split(";")[0] !== audioFormat.split(";")[0]
                ) {
                  console.error(
                    `Recorder produced ${actual} but session declared ${audioFormat}`,
                  );
                  speakingSocket.current?.close();
                  recorderRef.current?.stop();
                  recorderRef.current = null;
                  setError(
                    "Your browser recorded an unexpected audio format. Please try again.",
                  );
                  setState("idle");
                  setAudioStream(null);
                }
              })
              .catch((err) => {
                console.error("Failed to start audio recorder:", err);
                setError(
                  err instanceof Error &&
                    err.name === "UnsupportedRecordingError"
                    ? err.message
                    : "Could not start recording from your microphone.",
                );
                setState("idle");
              });
            break;

          case "recording":
            setState("listening");
            break;

          case "processing":
            setState("transcribing");
            clearTranscriptionTimeout();
            transcriptionTimeoutRef.current = setTimeout(() => {
              transcriptionTimeoutRef.current = null;
              setError("Transcription is taking longer than expected. Please try again.");
              setState("idle");
            }, 15000);
            break;

          case "done":
            setState("done");
            break;

          case "error":
            clearTranscriptionTimeout();
            setState("idle");
            setAudioStream(null);
            break;
        }
      },

      onEvaluation: (result) => {
        clearTranscriptionTimeout();
        setState("evaluating");
        setEvaluation(result);
        audioPlayer.current.play();
        setTimeout(() => setState("done"), 800);
      },
    });

    speakingSocket.current.connect();
  };

  const startSpeaking = async () => {
    setError(null);
    setEvaluation(null);

    try {
      if (navigator.mediaDevices?.getUserMedia) {
        const primingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        primingStream.getTracks().forEach((track) => track.stop());
      }
    } catch (e) {
      console.error("Mic permission error:", e);
      setError("Microphone permission is required to start a speaking session.");
      return;
    }

    setState("connecting");
    openSocket();
  };

  const stopSpeaking = () => {
    recorderRef.current?.stop();
    setAudioStream(null);
    speakingSocket.current?.finishRecording();
  };

  useEffect(() => {
    return () => {
      clearTranscriptionTimeout();
      recorderRef.current?.stop();
      speakingSocket.current?.close();
    };
  }, []);

  return (
    <div className="space-y-6">
      <SpeakingSessionPanel
        open
        transcript={transcript}
        state={state}
        error={error}
        audioStream={audioStream}
        sessionKey={sessionKey}
        onStart={startSpeaking}
        onStop={stopSpeaking}
        onClose={() => {
          clearTranscriptionTimeout();
          recorderRef.current?.stop();
          speakingSocket.current?.close();
          setAudioStream(null);
          setState("idle");
          setTranscript("");
          setError(null);
        }}
      />

      {evaluation && (
        <EvaluationBreakdown
          overallBand={evaluation.overall_band ?? null}
          criteria={extractCriteriaScores(evaluation.dimensions as SpeakingDimensions)}
          feedback={evaluation.overall_feedback}
          className="rounded-card border border-brand-border bg-surface p-6 shadow-e1"
        />
      )}
    </div>
  );
}
