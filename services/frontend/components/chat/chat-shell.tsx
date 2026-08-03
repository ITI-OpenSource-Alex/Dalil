"use client";
import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { streamChatResponse, ChatEvent } from "@/lib/chat-stream";
import MessageList from "./message-list";
import ChatInput from "./chat-input";
import SpeakingSessionPanel, { SpeakingState } from "./speaking-session-panel";
import { AudioRecorder } from "@/lib/audio-recorder";
import {
  SpeakingWebSocket,
  SpeakingEvaluation,
  SocketSpeakingState,
} from "@/lib/speaking-websocket";
import { AudioPlayer } from "@/lib/audio-player";

import EssayComposer from "./essay-composer";
import WritingEvaluationPanel from "./writing-evaluation-panel";

import { streamWritingEvaluation, WritingEvent } from "@/lib/writing-stream";
// Used by the inlineIssues state below. The type was referenced without being
// imported, so the frontend did not compile; that arrived on dev with the
// inline-feedback work and is not something this branch introduced.
import type { CriterionEvaluation } from "@/lib/writing-api";
import { SpeakingEvaluationResult } from "@/app/types/speaking";
import { extractCriteriaScores } from "@/lib/speaking-format";
import { CURRENT_USER_ID } from "@/lib/current-user";
import { getChatSessionId, startNewChatSession } from "@/lib/chat-session";

// The speaking service is reached directly from the browser — same rationale
// as lib/speaking-api.ts, which notes there's no gateway route for it. Derive
// the WebSocket origin from that same env var so one setting moves both the
// REST and WS endpoints together. http -> ws, https -> wss.
const SPEAKING_WS_URL =
  (process.env.NEXT_PUBLIC_SPEAKING_API_URL ?? "http://localhost:8082").replace(
    /^http/,
    "ws",
  ) + "/ws";

// Chat goes through the Gateway. These two calls used relative paths, i.e. to
// the Next.js server itself, where no route handler was ever written — both
// 404'd and surfaced as "Service unavailable" (BUG-044). The Gateway proxies
// them to Orchestration, adding JWT auth, rate limiting and correlation IDs.
//
// credentials: "include" is required because auth rides on HttpOnly cookies.
const CHAT_API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api`;

export type Opportunity = {
  // Present on every row RAG's /match returns (services/rag/app/services/scoring.py)
  // and passed through orchestration's match_results event unchanged, but this type
  // never declared it — GOA-035's "Get Checklist" entry point needs it to link to
  // /checklist/:programId.
  programId: string;
  programName: string;
  university: string;
  country: string;
  deadline: string;
  confidence: number; // 0 to 1
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  intent?: string;
  confidence?: number;
  opportunities?: Opportunity[];
  evaluation?: SpeakingEvaluationResult;
  sources?: string[];
  error?: string;
};

type ChatMode = "chat" | "writing";

export default function ChatShell() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi Lina 👋 I've loaded your profile (CGPA 3.45, IELTS 6). Where would you like to start?",
    },
  ]);
  const speakingSocket = useRef<SpeakingWebSocket | null>(null);
  const audioPlayer = useRef(new AudioPlayer());
  const audioPlayerRef = useRef<AudioContext | null>(null);

  const [isTyping, setIsTyping] = useState(false);
  const [speakingOpen, setSpeakingOpen] = useState(false);
  const [speakingState, setSpeakingState] = useState<SpeakingState>("idle");
  const [speakingEvaluation, setSpeakingEvaluation] =
    useState<SpeakingEvaluation | null>(null);
  const [speakingError, setSpeakingError] = useState<string | null>(null);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  // A real per-session id (GOA-038). This was the constant "session-lina-123",
  // shared by every browser, tab and reload, so a second conversation could not
  // exist -- and cross-session memory is only observable across two of them.
  //
  // Set in an effect because sessionStorage does not exist during SSR.
  const [sessionId, setSessionId] = useState<string>("");
  useEffect(() => {
    setSessionId(getChatSessionId());
  }, []);
  const [userId] = useState(CURRENT_USER_ID);
  const [memoryNotice, setMemoryNotice] = useState<string | null>(null);
  const [forgetting, setForgetting] = useState(false);
  const speakingQuestion = {
    prompt: "Describe a memorable journey you have taken.",
    type: "part2",
  };

  const recorderRef = useRef<AudioRecorder | null>(null);
  // Bumped once per new speaking session (see openSpeakingSocket). The only
  // job of this value is to tell RecordingTimer "a fresh take just began" —
  // it's not meaningful on its own and nothing else should read it.
  const [speakingSessionKey, setSpeakingSessionKey] = useState(0);
  // Stop -> finishRecording() is a local-only signal (see openSpeakingSocket's
  // "processing" case below); the server may never respond at all if
  // transcription fails silently server-side, so nothing else would ever
  // move speakingState off "transcribing". This is the fallback that does.
  const transcriptionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const [chatMode, setChatMode] = useState<ChatMode>("chat");
  const [writingLoading, setWritingLoading] = useState(false);
  const [writingEvaluations, setWritingEvaluations] = useState<
    Record<
      string,
      {
        band: number;
        feedback: string;
      }
    >
  >({});
  const [writingOverallBand, setWritingOverallBand] = useState<number>();
  const [inlineIssues, setInlineIssues] = useState<CriterionEvaluation[]>([]);
  const [submittedEssay, setSubmittedEssay] = useState<string>("");
  const [improvedEssay, setImprovedEssay] = useState<string | undefined>();
  const [isPaidTier] = useState(true); // TODO: hardcoded until tier comes from session/profile

  // Single source of truth for the session lock: which practice mode, if
  // any, currently owns the input area. Derived — not a separate flag — from
  // the two states that already govern what's on screen, so it can never
  // disagree with what the user is actually looking at. Whichever of these
  // is non-null is the one the *other* mode's controls get disabled for.
  const activePractice: "speaking" | "writing" | null = speakingOpen
    ? "speaking"
    : chatMode === "writing"
      ? "writing"
      : null;

  // Load session history on mount
  useEffect(() => {
    // Empty until the effect above reads sessionStorage. Fetching then would
    // request /chat/sessions//history, which is a different route entirely.
    if (!sessionId) return;

    async function loadHistory() {
      try {
        const res = await fetch(`${CHAT_API_BASE}/chat/sessions/${sessionId}/history`, {
          credentials: "include",
        });
        if (res.ok) {
          const history = await res.json();
          if (history && history.length > 0) {
            setMessages(
              history.map((h: any, idx: number) => ({
                id: `hist-${idx}`,
                role: h.role,
                content: h.content,
              })),
            );
          }
        }
      } catch (err) {
        console.error("Failed to fetch session history:", err);
      }
    }
    loadHistory();
  }, [sessionId]);

  /**
   * Start a fresh conversation (GOA-038).
   *
   * Only the short-term thread is abandoned. Long-term facts survive on
   * purpose — that is the entire feature: the next conversation should still
   * know your degree. Wiping them is the separate, explicit control below.
   */
  const handleNewConversation = () => {
    setSessionId(startNewChatSession());
    setMessages([]);
    setMemoryNotice(null);
    setChatMode("chat");
  };

  /**
   * Erase everything the assistant has stored about this user.
   *
   * Goes straight to the Gateway, not through a Next.js route handler. The
   * existing app/api/chat/route.ts proxies to Orchestration without any JWT
   * check; adding a second such route for a destructive endpoint would put an
   * unauthenticated erasure path on the frontend server.
   */
  const handleForgetMe = async () => {
    const confirmed = window.confirm(
      "Delete everything GOA remembers about you?\n\n" +
        "This removes your saved profile facts (degree, GPA, target country, " +
        "programmes and concerns) and your stored conversations. It cannot be undone.",
    );
    if (!confirmed) return;

    setForgetting(true);
    try {
      const res = await fetch(`${CHAT_API_BASE}/sessions/memory`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      const result = await res.json();
      // A new session id too: the old thread was just deleted server-side, so
      // continuing to post against it would recreate a conversation the user
      // asked to be rid of.
      setSessionId(startNewChatSession());
      setMessages([]);
      setMemoryNotice(
        `Deleted ${result.factsDeleted} saved fact${result.factsDeleted === 1 ? "" : "s"} ` +
          `and ${result.sessionsCleared} conversation${result.sessionsCleared === 1 ? "" : "s"}.`,
      );
    } catch (err) {
      console.error("Failed to delete stored memory:", err);
      // Never claim success here. Telling someone their data is gone when the
      // request failed is worse than telling them nothing.
      setMemoryNotice(
        "Could not delete your stored memory. Nothing was changed — please try again.",
      );
    } finally {
      setForgetting(false);
    }
  };

  const clearTranscriptionTimeout = () => {
    if (transcriptionTimeoutRef.current) {
      clearTimeout(transcriptionTimeoutRef.current);
      transcriptionTimeoutRef.current = null;
    }
  };

  // Opens a speaking session against `wsUrl`. Shared by the two ways a
  // session can start: the "Start Speaking" button (which knows the endpoint
  // directly) and a speaking_url SSE event (where Orchestration supplies it).
  const openSpeakingSocket = (wsUrl: string) => {
    // Every real "a new take is starting" entry point funnels through here
    // (the mic button and the chat-classified speaking_url path alike), so
    // this is the one place the timer's reset signal needs to fire.
    setSpeakingSessionKey((key) => key + 1);
    clearTranscriptionTimeout();
    speakingSocket.current?.close();

    speakingSocket.current = new SpeakingWebSocket({
      wsUrl,
      userId,
      questionPrompt: speakingQuestion.prompt,
      questionType: speakingQuestion.type,

      onTranscript: (text, isFinal) => {
        setLiveTranscript(text);

        if (isFinal) {
          console.log("Final transcript:", text);
        }
      },

      onTtsChunk: (audio) => {
        audioPlayer.current.addChunk(audio);
      },

      // Surface connection/server failures in the panel instead of leaving
      // the user staring at a silently-reset button. Must also move
      // speakingState back to "idle" itself — unlike the native-socket
      // "error" case below, nothing else does this for a server-sent error
      // message, which otherwise left the UI stuck on whatever state it was
      // in (e.g. "transcribing") forever.
      onError: (message) => {
        console.error("Speaking socket error:", message);
        clearTranscriptionTimeout();
        setSpeakingError(message);
        setSpeakingState("idle");
        setAudioStream(null);
      },

      onStateChange: (socketState) => {
        switch (socketState) {
          case "connecting":
            setSpeakingState("connecting");
            break;

          case "connected":
            setSpeakingState("listening");

            recorderRef.current = new AudioRecorder({
              onAudioChunk: (chunk) => {
                speakingSocket.current?.sendAudio(chunk);
              },
            });

            recorderRef.current
              .start()
              .then(() => {
                setAudioStream(recorderRef.current?.getStream() ?? null);
              })
              .catch((err) => {
                console.error("Failed to start audio recorder:", err);
                setSpeakingError(
                  "Could not start recording from your microphone.",
                );
                setSpeakingState("idle");
              });

            break;
          case "recording":
            setSpeakingState("listening");
            break;

          case "processing":
            setSpeakingState("transcribing");

            // Server-side transcription can fail without ever notifying the
            // client at all (e.g. the STT call times out) — finishRecording()
            // is a local-only signal with no server round trip, so nothing
            // else guarantees a reply arrives. Force back to "idle" if
            // neither onEvaluation nor onError happens within a generous
            // window, so the button can't get stuck on "Stop" forever.
            clearTranscriptionTimeout();
            transcriptionTimeoutRef.current = setTimeout(() => {
              transcriptionTimeoutRef.current = null;
              setSpeakingError(
                "Transcription is taking longer than expected. Please try again.",
              );
              setSpeakingState("idle");
            }, 15000);
            break;

          case "done":
            setSpeakingState("done");
            break;

          case "error":
            clearTranscriptionTimeout();
            setSpeakingState("idle");
            setAudioStream(null);
            break;
        }
      },

      onEvaluation: (evaluation) => {
        clearTranscriptionTimeout();
        setSpeakingState("evaluating");

        setSpeakingEvaluation(evaluation);

        setMessages((prev) => [
          ...prev,
          {
            id: `speaking-${Date.now()}`,
            role: "assistant",
            content: "Speaking evaluation completed.",
            evaluation: {
              overallScore: evaluation.overall_band,
              criteria: extractCriteriaScores(evaluation.dimensions),
              feedback: evaluation.overall_feedback,
            },
          },
        ]);

        audioPlayer.current.play();

        setTimeout(() => {
          setSpeakingState("done");
        }, 800);
      },
    });

    speakingSocket.current.connect();
  };

  const handleChatEvent = (event: ChatEvent, assistantMessageId: string) => {
    switch (event.type) {
      case "metadata":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  intent: event.intent,
                  confidence: event.confidence,
                }
              : m,
          ),
        );

        // First response received → stop typing indicator
        setIsTyping(false);
        break;

      case "token":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  content: m.content + event.content,
                }
              : m,
          ),
        );
        break;

      case "match_results":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  opportunities: event.programs,
                }
              : m,
          ),
        );
        break;

      case "sources":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  sources: event.sources,
                }
              : m,
          ),
        );
        break;

      case "writing_url":
        setWritingLoading(true);

        streamWritingEvaluation(event.sseUrl, handleWritingEvent).catch(
          console.error,
        );

        break;

      case "speaking_url":
        // A chat message classified as SPEAKING intent — Orchestration tells
        // us which endpoint to use.
        openSpeakingSocket(event.wsUrl);

        break;

      case "error":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  error: event.error,
                  content:
                    "Sorry, something went wrong while generating the response.",
                  isStreaming: false,
                }
              : m,
          ),
        );

        setIsTyping(false);
        // Only resets a session this response was itself trying to start —
        // leaves an unrelated in-progress/connected session alone.
        setSpeakingState((prev) => (prev === "connecting" ? "idle" : prev));
        break;
    }
  };

  const handleWritingEvent = (event: WritingEvent) => {
    switch (event.type) {
      case "criterion":
        setWritingEvaluations((prev) => ({
          ...prev,
          [event.criterion]: {
            band: event.band,
            feedback: event.feedback,
          },
        }));
        break;

      case "complete":
        setWritingEvaluations(event.evaluations);

        setWritingOverallBand(event.overall_band);

        setInlineIssues(event.evaluations_full);

        setImprovedEssay(event.improved_essay);

        setWritingLoading(false);

        break;

      case "error":
        console.error(event.error);

        setWritingLoading(false);

        break;
    }
  };

  // Send message to Orchestration
  const handleSendMessage = async (text: string) => {
    if (!text.trim()) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };

    setMessages((prev) => [...prev, userMessage]);

    setIsTyping(true);

    const assistantMessageId = `assistant-${Date.now()}`;

    const assistantMessage: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      isStreaming: true,
    };

    setMessages((prev) => [...prev, assistantMessage]);

    try {
      const response = await fetch(`${CHAT_API_BASE}/chat`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          userId,
          sessionId,
          message: text,
          attachments: [],
        }),
      });

      if (!response.ok) {
        throw new Error("Service unavailable");
      }

      await streamChatResponse(response, (event) =>
        handleChatEvent(event, assistantMessageId),
      );

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessageId
            ? {
                ...m,
                isStreaming: false,
              }
            : m,
        ),
      );

      setIsTyping(false);

      // The message that triggered this request may not have classified as
      // SPEAKING intent (e.g. supervisor routed it elsewhere), so no
      // "speaking_url" event ever arrived to move speakingState past
      // "connecting". Without this, the Start button would stay disabled
      // forever with nothing left to un-stick it.
      setSpeakingState((prev) => (prev === "connecting" ? "idle" : prev));
    } catch (error) {
      console.error(error);

      setIsTyping(false);

      setSpeakingState((prev) => (prev === "connecting" ? "idle" : prev));

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessageId
            ? {
                ...m,
                content:
                  "Sorry, I am having trouble connecting right now. Please try again later.",
                isStreaming: false,
              }
            : m,
        ),
      );
    }
  };

  const handleEssaySubmit = async (essay: string) => {
    setWritingEvaluations({});
    setWritingOverallBand(undefined);
    setInlineIssues([]);
    setSubmittedEssay(essay);
    setImprovedEssay(undefined);

    await handleSendMessage(essay);
  };

  const startSpeaking = async () => {
    setSpeakingOpen(true);
    setSpeakingError(null);

    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        // This call only exists to trigger the permission prompt eagerly;
        // the actual recording stream is acquired by AudioRecorder once the
        // WebSocket connects. Stop these tracks immediately so we don't
        // leave a live (but unused) mic stream open in the meantime.
        const primingStream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        primingStream.getTracks().forEach((track) => track.stop());
      }
    } catch (e) {
      console.error("Mic permission error:", e);
      setSpeakingError(
        "Microphone permission is required to start a speaking session.",
      );
      return;
    }

    // Connect straight to the speaking service rather than routing this
    // through /chat's LLM intent classifier.
    //
    // This button is unambiguous user intent, so there is nothing to
    // classify. Going via /chat made a dedicated button depend on a paid,
    // probabilistic LLM round trip, and when no Anthropic key is configured
    // classify_intent() falls back to RAG — no speaking_url is emitted, no
    // socket opens, and the whole speaking feature is dead. It also posted a
    // synthetic "I want to practice speaking" turn into the chat log as a
    // side effect of pressing a button.
    //
    // Free-text chat is genuinely ambiguous and still goes through the
    // classifier; the "speaking_url" case in handleChatEvent above keeps
    // that path working unchanged.
    //
    // speakingState stays out of "listening" until the socket actually
    // reaches "connected" (see onStateChange) — it only goes to "connecting"
    // here, which disables the button so a slow connect can't be
    // double-triggered.
    setSpeakingState("connecting");
    openSpeakingSocket(SPEAKING_WS_URL);
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
    <main className="min-h-screen flex flex-col bg-[#FAFBF9] text-[#1D291E]">
      {/* Top Banner indicating interactive session */}
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="border-b border-[#E8ECE7] px-8 py-4 bg-white flex items-center justify-between"
      >
        <div>
          <h1 className="text-lg font-bold text-[#0D3820]">GOA Assistant</h1>
          <p className="text-xs text-[#526053]">
            Lina Ahmadi • CGPA 3.45 • IELTS 6
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* GOA-038. Two different things, deliberately worded apart: one
              starts a new thread and keeps what the assistant knows about you,
              the other deletes it. */}
          <button
            type="button"
            onClick={handleNewConversation}
            className="text-xs px-3 py-1.5 rounded-full border border-[#E8ECE7] text-[#0D3820] hover:bg-[#F2F5F1] transition-colors"
          >
            New conversation
          </button>
          <button
            type="button"
            onClick={handleForgetMe}
            disabled={forgetting}
            title="Delete your saved profile facts and stored conversations"
            className="text-xs px-3 py-1.5 rounded-full border border-[#E8ECE7] text-[#8A3324] hover:bg-[#FBF1EF] transition-colors disabled:opacity-50"
          >
            {forgetting ? "Deleting…" : "Forget what you know about me"}
          </button>
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-[#526053]">Sync Ready</span>
        </div>
      </motion.div>

      {memoryNotice && (
        <div
          role="status"
          className="px-8 py-2 text-xs text-[#0D3820] bg-[#F2F5F1] border-b border-[#E8ECE7]"
        >
          {memoryNotice}
        </div>
      )}

      {/* Messages Wrapper */}
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.1 }}
        className="flex-1 overflow-y-auto px-8 py-6"
      >
        <MessageList messages={messages} isTyping={isTyping} />
      </motion.section>

      {/* Inputs Wrapper */}
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15, ease: "easeOut" }}
        className="border-t border-[#E8ECE7] bg-white px-8 py-4"
      >
        <SpeakingSessionPanel
          open={speakingOpen}
          transcript={liveTranscript}
          state={speakingState}
          error={speakingError}
          audioStream={audioStream}
          sessionKey={speakingSessionKey}
          disabledReason={
            activePractice === "writing"
              ? "Finish the current Writing session before starting Speaking Practice."
              : undefined
          }
          onStart={startSpeaking}
          onStop={stopSpeaking}
          onClose={() => {
            clearTranscriptionTimeout();
            recorderRef.current?.stop();
            setAudioStream(null);
            setSpeakingOpen(false);
            setSpeakingState("idle");
            setLiveTranscript("");
            setSpeakingError(null);
          }}
        />
        {chatMode === "chat" ? (
          <ChatInput
            onSendMessage={handleSendMessage}
            onOpenSpeaking={() => setSpeakingOpen(true)}
            onOpenWriting={() => setChatMode("writing")}
            activePractice={activePractice}
          />
        ) : (
          <div className="space-y-4">
            <EssayComposer
              loading={writingLoading}
              onSubmit={handleEssaySubmit}
              onCancel={() => setChatMode("chat")}
            />

            <WritingEvaluationPanel
              evaluations={writingEvaluations}
              overallBand={writingOverallBand}
              loading={writingLoading}
              inlineIssues={inlineIssues}
              essayText={submittedEssay}
              improvedEssay={improvedEssay}
              isPaidTier={isPaidTier}
            />
          </div>
        )}
        <div className="text-center text-[11px] text-[#A2ADA3] mt-2">
          GOA can make mistakes. Verify university requirements before applying.
        </div>
      </motion.section>
    </main>
  );
}