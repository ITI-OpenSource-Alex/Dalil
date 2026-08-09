"use client";

import { useEffect, useRef, useState } from "react";
import SpeakingSessionPanel, { SpeakingState } from "@/components/chat/speaking-session-panel";
import EvaluationBreakdown from "@/components/speaking/evaluation-breakdown";
import { AudioRecorder, selectRecordingMimeType } from "@/lib/audio-recorder";
import {
  ExaminerTurn,
  SpeakingCueCard,
  SpeakingEvaluation,
  SpeakingWebSocket,
} from "@/lib/speaking-websocket";
import { AudioPlayer } from "@/lib/audio-player";
import { SpeakingDimensions } from "@/app/types/speaking";
import { extractCriteriaScores } from "@/lib/speaking-format";
import { CURRENT_USER_ID } from "@/lib/current-user";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";

const SPEAKING_WS_URL =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080").replace(/^http/, "ws") +
  "/api/speaking/ws";
const RESUME_STORAGE_KEY = "dalil:speaking:active-session";

export default function SpeakingPracticePanel() {
  const speakingSocket = useRef<SpeakingWebSocket | null>(null);
  const audioPlayer = useRef(new AudioPlayer());
  const recorderRef = useRef<AudioRecorder | null>(null);
  const pendingExaminerTurn = useRef<ExaminerTurn | null>(null);
  const examinerTurns = useRef(new Map<string, ExaminerTurn>());
  const playback = useRef(new Map<string, Promise<void>>());
  const audioFormatRef = useRef("");
  const acceptRecorderChunks = useRef(false);
  const partRef = useRef<1 | 2 | 3>(1);
  const cueCardRef = useRef<SpeakingCueCard | null>(null);
  const recordingTurnID = useRef<string | null>(null);

  const [state, setState] = useState<SpeakingState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState("");
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [sessionKey, setSessionKey] = useState(0);
  const [evaluation, setEvaluation] = useState<SpeakingEvaluation | null>(null);
  const [part, setPart] = useState<1 | 2 | 3>(1);
  const [partLabel, setPartLabel] = useState("Introduction and interview");
  const [examinerText, setExaminerText] = useState("");
  const [cueCard, setCueCard] = useState<SpeakingCueCard | null>(null);
  const [timerEndsAt, setTimerEndsAt] = useState<number | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);

  const { user } = useCurrentUser();
  const userId = user?.id ?? CURRENT_USER_ID;

  useEffect(() => {
    if (timerEndsAt === null) {
      setRemainingSeconds(null);
      return;
    }
    const update = () => setRemainingSeconds(Math.max(0, Math.ceil((timerEndsAt - Date.now()) / 1000)));
    update();
    const interval = window.setInterval(update, 250);
    return () => window.clearInterval(interval);
  }, [timerEndsAt]);

  const stopRecorder = async (sendAudioEnd: boolean) => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    if (!sendAudioEnd) acceptRecorderChunks.current = false;
    if (recorder) await recorder.stop();
    acceptRecorderChunks.current = false;
    setAudioStream(null);
    if (sendAudioEnd) speakingSocket.current?.finishRecording();
  };

  const startTurnRecording = async () => {
    await stopRecorder(false);
    const recorder = new AudioRecorder({
      onAudioChunk: (chunk) => {
        if (acceptRecorderChunks.current) speakingSocket.current?.sendAudio(chunk);
      },
    });
    recorderRef.current = recorder;
    try {
      await recorder.start();
      acceptRecorderChunks.current = true;
      const actual = recorder.getMimeType();
      if (actual && actual.split(";")[0] !== audioFormatRef.current.split(";")[0]) {
        throw new Error(`Recorder produced ${actual} after declaring ${audioFormatRef.current}.`);
      }
      setAudioStream(recorder.getStream());
      setState("listening");
    } catch (recordingError) {
      setError(recordingError instanceof Error ? recordingError.message : "Could not start your microphone.");
      setState("error");
    }
  };

  const afterExaminerTurn = async (turnId: string) => {
    const turn = examinerTurns.current.get(turnId);
    if (!turn) return;
    try {
      await playback.current.get(turnId);
    } catch {
      // The written question remains authoritative when local playback fails.
    }
    if (turn.question_id === "script.part1.intro") {
      speakingSocket.current?.ready();
    } else if (turn.expects_response) {
      if (recordingTurnID.current !== turn.turn_id) {
        recordingTurnID.current = turn.turn_id;
        await startTurnRecording();
      }
    } else if (cueCardRef.current && turn.question_id === cueCardRef.current.cue_id) {
      speakingSocket.current?.ready();
    }
  };

  const openSocket = (audioFormat: string) => {
    const resumeSessionId = window.localStorage.getItem(RESUME_STORAGE_KEY) ?? undefined;
    audioFormatRef.current = audioFormat;
    speakingSocket.current?.close();
    speakingSocket.current = new SpeakingWebSocket({
      wsUrl: SPEAKING_WS_URL,
      userId,
      audioFormat,
      resumeSessionId,
      onStateChange: (socketState) => {
        if (socketState === "connecting") setState("connecting");
        if (socketState === "connected") setState("examiner");
        if (socketState === "processing") setState("transcribing");
        if (socketState === "error") setState("error");
      },
      onSessionStarted: (sessionId) => window.localStorage.setItem(RESUME_STORAGE_KEY, sessionId),
      onSessionResumed: (resumedPart) => setPart(resumedPart as 1 | 2 | 3),
      onPartChange: (change) => {
        partRef.current = change.part;
        setPart(change.part);
        setPartLabel(change.part_label);
        if (change.part !== 2) {
          cueCardRef.current = null;
          setCueCard(null);
        }
      },
      onExaminerTurn: (turn) => {
        void stopRecorder(false);
        pendingExaminerTurn.current = turn;
        examinerTurns.current.set(turn.turn_id, turn);
        recordingTurnID.current = null;
        setExaminerText(turn.text);
        setState("examiner");
      },
      onTtsChunk: (audio) => {
        const turn = pendingExaminerTurn.current;
        if (!turn) return;
        playback.current.set(turn.turn_id, audioPlayer.current.queueExaminerTurn(audio));
      },
      onExaminerAudioEnd: (turnId) => void afterExaminerTurn(turnId),
      onCueCard: (card) => {
        cueCardRef.current = card;
        setCueCard(card);
      },
      onPrepStart: (timer) => {
        setState("preparing");
        setTimerEndsAt(timer.ends_at ? Date.parse(timer.ends_at) : Date.now() + (timer.duration_s ?? 60) * 1000);
      },
      onPrepEnd: () => setTimerEndsAt(null),
      onLongTurnStart: (timer) => {
        setTimerEndsAt(timer.ends_at ? Date.parse(timer.ends_at) : Date.now() + (timer.max_s ?? 120) * 1000);
        void startTurnRecording();
      },
      onLongTurnContinue: (timer) => {
        setRemainingSeconds(timer.remaining_s ?? null);
        void startTurnRecording();
      },
      onTranscript: (text) => {
        setTranscript((current) => current ? `${current}\n\nPart ${partRef.current}: ${text}` : `Part ${partRef.current}: ${text}`);
      },
      onSessionComplete: () => {
        void stopRecorder(false);
        setTimerEndsAt(null);
        setState("evaluating");
        window.localStorage.removeItem(RESUME_STORAGE_KEY);
      },
      onEvaluation: (result) => {
        setEvaluation(result);
        setState("done");
      },
      onError: (message) => {
        setError(message);
        setState("error");
        if (message.includes("resume") || message.includes("already")) {
          window.localStorage.removeItem(RESUME_STORAGE_KEY);
        }
      },
    });
    speakingSocket.current.connect();
  };

  const startSpeaking = async () => {
    setError(null);
    setEvaluation(null);
    setTranscript("");
    setCueCard(null);
    setExaminerText("");
    setPart(1);
    partRef.current = 1;
    cueCardRef.current = null;
    setPartLabel("Introduction and interview");
    setSessionKey((key) => key + 1);
    try {
      const audioFormat = selectRecordingMimeType();
      const primingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      primingStream.getTracks().forEach((track) => track.stop());
      setState("connecting");
      openSocket(audioFormat);
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "Microphone permission is required.");
      setState("error");
    }
  };

  const stopSpeaking = () => void stopRecorder(true);

  const bargeIn = () => {
    const turn = pendingExaminerTurn.current;
    if (!turn?.expects_response || recordingTurnID.current === turn.turn_id) return;
    recordingTurnID.current = turn.turn_id;
    audioPlayer.current.stop();
    void startTurnRecording();
  };

  const closeSpeaking = () => {
    speakingSocket.current?.abandon();
    void stopRecorder(false);
    audioPlayer.current.stop();
    speakingSocket.current?.close();
    setState("idle");
    setTimerEndsAt(null);
  };

  useEffect(() => () => {
    void stopRecorder(false);
    audioPlayer.current.stop();
    speakingSocket.current?.close();
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
        part={part}
        partLabel={partLabel}
        examinerText={examinerText}
        cueCard={cueCard}
        remainingSeconds={remainingSeconds}
        onStart={startSpeaking}
        onStop={stopSpeaking}
        onClose={closeSpeaking}
        canBargeIn={Boolean(pendingExaminerTurn.current?.expects_response)}
        onBargeIn={bargeIn}
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
