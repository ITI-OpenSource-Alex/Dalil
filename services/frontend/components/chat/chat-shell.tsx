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
import {
  SpeakingDimensions,
  SpeakingEvaluationResult,
} from "@/app/types/speaking";
import { extractCriteriaScores } from "@/lib/speaking-format";
import { CURRENT_USER_ID } from "@/lib/current-user";
import { getChatSessionId, startNewChatSession } from "@/lib/chat-session";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import InlineAlert from "@/components/speaking/inline-alert";
import {
  CONNECTION_ERROR,
  GENERIC_ASSISTANT_ERROR,
  sanitizeAssistantText,
  sanitizeErrorMessage,
} from "@/lib/chat-sanitize";
import {
  isSubscriptionRequiredMessage,
  SubscriptionRequiredError,
} from "@/lib/subscription";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";

// GOA-132: the speaking socket now goes through the Gateway like every other
// browser call, so it picks up JWT validation at upgrade time, rate limiting
// and a correlation ID. NEXT_PUBLIC_SPEAKING_API_URL is gone — it pointed the
// browser straight at :8082, which had none of those.
//
// Derived from the single Gateway URL so the two cannot drift. http -> ws,
// https -> wss. Orchestration also emits this URL on the speaking_url event;
// this constant is the fallback when the socket is opened without a chat turn.
const SPEAKING_WS_URL =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080").replace(
    /^http/,
    "ws",
  ) + "/api/speaking/ws";

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
  // Nullable: the column is optional in program_requirements and RAG
  // passes None straight through, which the UI rendered as "Deadline: null".
  deadline: string | null;
  // The real /match response nests the score under `result.score` on a 0-100
  // scale (services/rag/app/services/scoring.py's match_programs) -- this type
  // previously declared a flat `confidence: number` on a 0-1 scale that never
  // matched any real field name, so every card rendered "NaN% Match" (masked
  // until now by an unrelated SSE-parsing bug that prevented match_results
  // from ever reaching the UI at all).
  result: {
    score: number;
    blocked_by: string | null;
  };
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

/**
 * Message ids used to be `assistant-${Date.now()}`. Two sends inside the same
 * millisecond -- which is exactly what a double-fired submit produces -- gave
 * two messages the same id, so `<AnimatePresence>` saw duplicate React keys and
 * every `messages.map(m => m.id === assistantMessageId ? ... : m)` update wrote
 * tokens into *both* bubbles. That is one of the ways the same answer appeared
 * to be streamed twice. A monotonic counter cannot collide.
 */
let messageSequence = 0;
function nextMessageId(prefix: string): string {
  messageSequence += 1;
  return `${prefix}-${messageSequence}-${Date.now()}`;
}

export default function ChatShell() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi 👋 I can help you find Master's programs, build an application checklist, or practise IELTS — where would you like to start?",
    },
  ]);
  const speakingSocket = useRef<SpeakingWebSocket | null>(null);
  const audioPlayer = useRef(new AudioPlayer());
  const audioPlayerRef = useRef<AudioContext | null>(null);

  const [isTyping, setIsTyping] = useState(false);
  const upgrade = useUpgradePrompt();
  /*
   * The single-flight lock on sending.
   *
   * handleSendMessage had no guard at all, and there are three ways to invoke
   * it in quick succession: Enter in the textarea, the Send button, and the
   * Writing composer's submit. Each invocation appended its own assistant
   * bubble and opened its own POST /api/chat, so two replies really did stream
   * side by side for one apparent question -- the "two assistants answering"
   * report. A ref, not state: the second call happens in the same tick as the
   * first, before any re-render could have propagated a state flag.
   */
  const sendingRef = useRef(false);
  const [isSending, setIsSending] = useState(false);
  /** True once anything has been sent, so history can no longer clobber. */
  const hasSentRef = useRef(false);
  /** Aborts an in-flight turn when the conversation is reset or unmounted. */
  const chatAbortRef = useRef<AbortController | null>(null);
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
  // GOA-035/BUG-047: userId comes from the authenticated profile, falling
  // back to CURRENT_USER_ID only until it resolves (or if it errors) -- see
  // lib/current-user.ts.
  //
  // The session id deliberately stays GOA-038's sessionStorage value rather
  // than being derived from userId as `chat-${userId}`: startNewChatSession()
  // below has to mint a fresh conversation for the same user, which a value
  // derived from identity alone cannot express.
  const {
    user,
    status: profileStatus,
    error: profileError,
    retry: retryProfile,
  } = useCurrentUser();
  const identityLoading =
    profileStatus === "loading" || profileStatus === "idle";
  const userId = user?.id ?? CURRENT_USER_ID;
  // Replaces the hardcoded "LA" on the user avatar — a leftover from the
  // "Lina Ahmadi" demo persona that showed the same two letters to everyone.
  const userInitials = (user?.email?.split("@")[0] ?? "")
    .replace(/[^a-zA-Z]/g, "")
    .slice(0, 2)
    .toUpperCase();
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
  // Surfaces both an SSE-stream "error" event from the writing service and a
  // failure to even open the stream (e.g. an auth/subscription rejection
  // from the Gateway) -- previously either case only reached console.error,
  // leaving writingLoading stuck true with nothing visible to the user.
  const [writingError, setWritingError] = useState<string | null>(null);
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

    // Two guards, for two different ways this effect used to corrupt the
    // transcript:
    //
    // 1. AbortController + the `cancelled` flag. In development React mounts
    //    effects twice, so this fired two overlapping history requests whose
    //    responses both called setMessages. It is also what keeps a response
    //    from a session the user has already left (New conversation, Forget
    //    me) from landing in the new one.
    //
    // 2. hasSentRef. loadHistory *replaces* the whole message list. If the
    //    user typed and sent before this slow GET resolved, the replacement
    //    wiped the user's message and the assistant bubble that was actively
    //    streaming into it -- after which every token update targeted an id
    //    that no longer existed, and the reply appeared to restart from
    //    nothing. History is only ever applied to an untouched transcript.
    const controller = new AbortController();
    let cancelled = false;

    async function loadHistory() {
      try {
        const res = await fetch(`${CHAT_API_BASE}/chat/sessions/${sessionId}/history`, {
          credentials: "include",
          signal: controller.signal,
        });
        if (cancelled || hasSentRef.current) return;
        if (res.ok) {
          const history = await res.json();
          if (cancelled || hasSentRef.current) return;

          // doc 10: history was assumed to always be an array of
          // {role, content} entries and mapped over unguarded -- a
          // non-array 200 response (or a malformed entry within an
          // otherwise-valid array) threw during render instead of
          // degrading gracefully. Malformed entries are skipped
          // individually rather than passed through with undefined
          // role/content, so one bad entry doesn't blank out an
          // otherwise-good history.
          if (Array.isArray(history)) {
            const validMessages: Message[] = [];

            history.forEach((h: unknown, idx: number) => {
              const entry = h as { role?: unknown; content?: unknown } | null;
              if (
                entry &&
                (entry.role === "user" || entry.role === "assistant") &&
                typeof entry.content === "string"
              ) {
                validMessages.push({
                  // Namespaced by session id: `hist-0` from a previous
                  // conversation could otherwise collide with `hist-0` from
                  // this one if both ended up in the list.
                  id: `hist-${sessionId}-${idx}`,
                  role: entry.role,
                  content:
                    entry.role === "assistant"
                      ? sanitizeAssistantText(entry.content)
                      : entry.content,
                });
              }
            });

            if (validMessages.length > 0 && !cancelled && !hasSentRef.current) {
              setMessages(validMessages);
            }
          }
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        console.error("Failed to fetch session history:", err);
      }
    }
    loadHistory();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [sessionId]);

  /**
   * Start a fresh conversation (GOA-038).
   *
   * Only the short-term thread is abandoned. Long-term facts survive on
   * purpose — that is the entire feature: the next conversation should still
   * know your degree. Wiping them is the separate, explicit control below.
   */
  const handleNewConversation = () => {
    // Cut any in-flight turn loose first. Without this, a reply still
    // streaming from the abandoned conversation kept appending tokens into
    // the new one's (empty) transcript, which looked exactly like an
    // unprompted second assistant message.
    chatAbortRef.current?.abort();
    chatAbortRef.current = null;
    sendingRef.current = false;
    setIsSending(false);
    setIsTyping(false);

    setSessionId(startNewChatSession());
    setMessages([]);
    setMemoryNotice(null);
    setChatMode("chat");
    // Lets the new session's history load apply again — it is a different
    // conversation, and nothing has been sent in it yet.
    hasSentRef.current = false;
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
      chatAbortRef.current?.abort();
      chatAbortRef.current = null;
      sendingRef.current = false;
      setIsSending(false);
      setIsTyping(false);
      hasSentRef.current = false;
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
              overallScore: evaluation.overall_band ?? null,
              criteria: extractCriteriaScores(
                evaluation.dimensions as SpeakingDimensions,
              ),
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
        setWritingError(null);

        // Failing to even open the stream (e.g. a 401 from the Gateway when
        // the auth cookie or subscription tier doesn't clear) is otherwise a
        // dead end -- the panel is left spinning forever with nothing but a
        // console log. Reset the loading flag and surface it the same way an
        // in-stream "error" event does (see handleWritingEvent above).
        streamWritingEvaluation(event.sseUrl, handleWritingEvent).catch(
          (err) => {
            setWritingLoading(false);
            // A 403 here is the paid-tier gate on
            // /api/writing/essays/:id/evaluate, not a fault. It used to render
            // as "Unable to start writing evaluation (status 403)." in the
            // panel; it now opens the upgrade dialog and says so plainly.
            if (upgrade.handle(err, "essay-evaluation")) {
              setWritingError(
                "Essay evaluation is part of GOA Pro — see the upgrade details.",
              );
              return;
            }
            console.error(err);
            setWritingError(
              sanitizeErrorMessage(
                err instanceof Error ? err.message : undefined,
              ),
            );
          },
        );

        break;

      case "speaking_url":
        // A chat message classified as SPEAKING intent — Orchestration tells
        // us which endpoint to use.
        openSpeakingSocket(event.wsUrl);

        break;

      case "error": {
        // Orchestration sends the bare marker "subscription_required" for an
        // intent the account's tier doesn't cover (app/api/chat.py). Printing
        // that token was the chat-side version of the raw 403 the exam page
        // used to show; it now opens the same upgrade dialog as everywhere
        // else. Every other error is passed through the sanitiser so a
        // stringified backend exception can never reach the transcript.
        const isPaywall = isSubscriptionRequiredMessage(event.error);
        if (isPaywall) upgrade.show();

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  error: event.error,
                  content: isPaywall
                    ? "That one needs GOA Pro — I've opened the details for you."
                    : sanitizeErrorMessage(event.error),
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
        setWritingError(event.error);

        break;
    }
  };

  // Send message to Orchestration
  const handleSendMessage = async (text: string) => {
    if (!text.trim()) return;

    // Exactly one turn may be in flight. A second submit while a reply is
    // streaming is dropped here rather than producing a second bubble and a
    // second POST -- see sendingRef's declaration for why this is a ref.
    if (sendingRef.current) return;
    sendingRef.current = true;
    hasSentRef.current = true;
    setIsSending(true);

    const controller = new AbortController();
    // Supersede rather than accumulate: if a previous turn somehow survived
    // (a reset raced the stream), its reader is cut loose here so it cannot
    // keep writing tokens into a transcript that has moved on.
    chatAbortRef.current?.abort();
    chatAbortRef.current = controller;

    const userMessage: Message = {
      id: nextMessageId("user"),
      role: "user",
      content: text,
    };

    setIsTyping(true);

    const assistantMessageId = nextMessageId("assistant");

    const assistantMessage: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      isStreaming: true,
    };

    // Both messages appended in one update. As two separate setMessages calls
    // they could interleave with an event handler's own update between them.
    setMessages((prev) => [...prev, userMessage, assistantMessage]);

    try {
      const response = await fetch(`${CHAT_API_BASE}/chat`, {
        method: "POST",
        credentials: "include",
        signal: controller.signal,
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
        // Chat itself is a free-tier route, but the intents it dispatches to
        // are not all free. Surface the paywall as the paywall.
        if (response.status === 403) {
          throw new SubscriptionRequiredError(null);
        }
        throw new Error(`Chat request failed with status ${response.status}`);
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
                // A turn that produced no text at all (every event was an
                // attachment, or the stream closed early) previously left an
                // empty bubble with a blinking cursor forever.
                content:
                  m.content.trim() ||
                  (m.opportunities?.length || m.sources?.length
                    ? m.content
                    : GENERIC_ASSISTANT_ERROR),
              }
            : m,
        ),
      );

      // The message that triggered this request may not have classified as
      // SPEAKING intent (e.g. supervisor routed it elsewhere), so no
      // "speaking_url" event ever arrived to move speakingState past
      // "connecting". Without this, the Start button would stay disabled
      // forever with nothing left to un-stick it.
      setSpeakingState((prev) => (prev === "connecting" ? "idle" : prev));
    } catch (error) {
      // An aborted turn is not a failure: the user reset the conversation or
      // left the page. Writing an error into a bubble that no longer exists
      // (or is about to be discarded) would be noise.
      if (controller.signal.aborted) return;

      const wasPaywall = upgrade.handle(error, "writing-practice");
      if (!wasPaywall) console.error(error);

      setSpeakingState((prev) => (prev === "connecting" ? "idle" : prev));

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessageId
            ? {
                ...m,
                content: wasPaywall
                  ? "That one needs GOA Pro — I've opened the details for you."
                  : CONNECTION_ERROR,
                isStreaming: false,
              }
            : m,
        ),
      );
    } finally {
      if (chatAbortRef.current === controller) chatAbortRef.current = null;
      sendingRef.current = false;
      setIsSending(false);
      setIsTyping(false);
    }
  };

  const handleEssaySubmit = async (essay: string) => {
    setWritingEvaluations({});
    setWritingOverallBand(undefined);
    setInlineIssues([]);
    setSubmittedEssay(essay);
    setImprovedEssay(undefined);
    setWritingError(null);

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
      // An unfinished SSE read left running past unmount kept calling
      // setMessages on a dead component, and — because sessionStorage keeps
      // the session id — its tokens reappeared in the transcript when the
      // page was navigated back to.
      chatAbortRef.current?.abort();
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
            {profileStatus === "success" && user
              ? user.email
              : identityLoading
                ? "Loading your profile…"
                : "Not signed in"}
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
        <MessageList
          messages={messages}
          isTyping={isTyping}
          userInitials={userInitials}
        />
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
        {profileStatus === "error" && (
          <div className="mb-3">
            <InlineAlert
              title="Couldn't load your profile"
              description={
                profileError ??
                "Chat will keep using a placeholder identity until this is retried."
              }
              onRetry={retryProfile}
            />
          </div>
        )}
        {chatMode === "chat" ? (
          <ChatInput
            onSendMessage={handleSendMessage}
            onOpenSpeaking={() => setSpeakingOpen(true)}
            onOpenWriting={() => setChatMode("writing")}
            activePractice={activePractice}
            disabled={identityLoading}
            sending={isSending}
          />
        ) : (
          <div className="space-y-4">
            <EssayComposer
              loading={writingLoading}
              onSubmit={handleEssaySubmit}
              onCancel={() => {
                setChatMode("chat");
                setWritingError(null);
              }}
            />

            <WritingEvaluationPanel
              evaluations={writingEvaluations}
              overallBand={writingOverallBand}
              loading={writingLoading}
              inlineIssues={inlineIssues}
              essayText={submittedEssay}
              improvedEssay={improvedEssay}
              isPaidTier={isPaidTier}
              error={writingError}
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