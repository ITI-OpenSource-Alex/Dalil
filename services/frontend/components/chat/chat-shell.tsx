"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Plus, RotateCcw, Sparkles, Trash2, X } from "lucide-react";
import { streamChatResponse, ChatEvent } from "@/lib/chat-stream";
import MessageList from "./message-list";
import ChatInput from "./chat-input";
import { CURRENT_USER_ID } from "@/lib/current-user";
import { emailInitials } from "@/lib/user-display";
import { getChatSessionId, startNewChatSession } from "@/lib/chat-session";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { Alert, Button } from "@/components/ui";
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
import type { ExplanationContext } from "@/lib/explanation-context";

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
  streamingStatus?: string;
  intent?: string;
  confidence?: number;
  opportunities?: Opportunity[];
  sources?: string[];
  error?: string;
};

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

interface ChatShellProps {
  variant?: "page" | "widget";
  draft?: string;
  onDraftChange?: (value: string) => void;
  explanationContext?: ExplanationContext | null;
  onClearExplanationContext?: () => void;
  focusRequestKey?: number;
  onClose?: () => void;
  onBusyChange?: (busy: boolean) => void;
  onResponseComplete?: () => void;
}

export default function ChatShell({
  variant = "page",
  draft,
  onDraftChange,
  explanationContext = null,
  onClearExplanationContext,
  focusRequestKey,
  onClose,
  onBusyChange,
  onResponseComplete,
}: ChatShellProps) {
  const isWidget = variant === "widget";
  const [internalDraft, setInternalDraft] = useState("");
  const composerDraft = draft ?? internalDraft;
  const setComposerDraft = onDraftChange ?? setInternalDraft;
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi 👋 I can help you find Master's programs, build an application checklist, or practise IELTS — where would you like to start?",
    },
  ]);
  const router = useRouter();
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
  const userInitials = user?.email ? emailInitials(user.email) : "";
  const [memoryNotice, setMemoryNotice] = useState<string | null>(null);
  const [forgetting, setForgetting] = useState(false);
  const [confirmingForget, setConfirmingForget] = useState(false);

  useEffect(() => {
    onBusyChange?.(isSending);
  }, [isSending, onBusyChange]);

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
    setComposerDraft("");
    onClearExplanationContext?.();
    setMemoryNotice(null);
    setConfirmingForget(false);
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
  const handleForgetMe = async (skipConfirmation = false) => {
    if (!skipConfirmation) {
      const confirmed = window.confirm(
        "Delete everything Dalil remembers about you?\n\n" +
          "This removes your saved profile facts (degree, GPA, target country, " +
          "programmes and concerns) and your stored conversations. It cannot be undone.",
      );
      if (!confirmed) return;
    }

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
      setComposerDraft("");
      onClearExplanationContext?.();
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
      setConfirmingForget(false);
    }
  };

  const handleChatEvent = (event: ChatEvent, assistantMessageId: string) => {
    switch (event.type) {
      case "status":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? { ...m, streamingStatus: event.message }
              : m,
          ),
        );
        break;

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

        break;

      case "token":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMessageId
              ? {
                  ...m,
                  content: m.content + event.content,
                  streamingStatus: undefined,
                }
              : m,
          ),
        );
        // Metadata only confirms routing. The visible progress animation stays
        // active until real answer text arrives.
        setIsTyping(false);
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
        // A chat message classified as WRITING intent -- Orchestration
        // already created the essay server-side (see the Writing service's
        // POST /essays) and hands back its id. Writing Practice now has its
        // own page (Phase D); hand the id off via query param so that page
        // picks up evaluating this essay instead of the user's typed text
        // going to waste. See WritingPracticePanel's essayId effect.
        router.push(`/practice/writing?essayId=${encodeURIComponent(event.essayId)}`);
        break;

      case "speaking_url":
        // A chat message classified as SPEAKING intent. Speaking Practice
        // now has its own page (Phase D) that opens its own session, so
        // there's nothing left for chat-shell to connect here -- just send
        // the user to it.
        router.push("/practice/speaking");
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
                    ? "That one needs Dalil Pro — I've opened the details for you."
                    : sanitizeErrorMessage(event.error),
                  isStreaming: false,
                }
              : m,
          ),
        );

        setIsTyping(false);
        break;
      }
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
    const turnExplanationContext = explanationContext;
    if (turnExplanationContext) onClearExplanationContext?.();

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
      streamingStatus: "Connecting to Dalil…",
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
          explanationContext: turnExplanationContext ?? undefined,
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
    } catch (error) {
      // An aborted turn is not a failure: the user reset the conversation or
      // left the page. Writing an error into a bubble that no longer exists
      // (or is about to be discarded) would be noise.
      if (controller.signal.aborted) return;

      const wasPaywall = upgrade.handle(error, "writing-practice");
      if (!wasPaywall) console.error(error);

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessageId
            ? {
                ...m,
                content: wasPaywall
                  ? "That one needs Dalil Pro — I've opened the details for you."
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
      if (!controller.signal.aborted) onResponseComplete?.();
    }
  };

  useEffect(() => {
    return () => {
      // An unfinished SSE read left running past unmount kept calling
      // setMessages on a dead component, and — because sessionStorage keeps
      // the session id — its tokens reappeared in the transcript when the
      // page was navigated back to.
      chatAbortRef.current?.abort();
    };
  }, []);

  return (
    <div
      className={`${isWidget ? "h-full min-h-0" : "min-h-screen"} flex flex-col bg-canvas text-fg`}
    >
      {/* Top Banner indicating interactive session */}
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className={`border-b border-border bg-surface flex gap-3 ${
          isWidget
            ? "items-center justify-between px-4 py-3"
            : "flex-col px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-8"
        }`}
      >
        <div>
          <h1 className="text-lg font-bold text-brand-fg">Dalil Assistant</h1>
          <p className="text-xs text-fg-muted">
            {isWidget
              ? "Ask anything, or refine a suggested prompt"
              : profileStatus === "success" && user
                ? user.email
                : identityLoading
                  ? "Loading your profile…"
                  : "Not signed in"}
          </p>
        </div>
        {/* flex-wrap: "New conversation" + "Forget what you know about me" +
            the sync indicator don't fit in one unbroken row under ~500px --
            they used to clip past the edge of the screen instead of wrapping. */}
        {isWidget ? (
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              iconOnly
              aria-label="Start a new conversation"
              title="New conversation"
              onClick={handleNewConversation}
              leadingIcon={Plus}
            />
            <Button
              variant="ghost"
              size="sm"
              iconOnly
              aria-label="Forget what Dalil knows about me"
              title="Forget what Dalil knows about me"
              onClick={() => setConfirmingForget(true)}
              leadingIcon={Trash2}
            />
            <Button
              variant="ghost"
              size="sm"
              iconOnly
              aria-label="Close Dalil chat"
              title="Close"
              onClick={onClose}
              leadingIcon={X}
            />
          </div>
        ) : (
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* GOA-038. Two different things, deliberately worded apart: one
              starts a new thread and keeps what the assistant knows about you,
              the other deletes it. */}
          <button
            type="button"
            onClick={handleNewConversation}
            className="text-xs px-3 py-1.5 rounded-full border border-border text-brand-fg hover:bg-canvas-subtle transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
          >
            New conversation
          </button>
          <button
            type="button"
            onClick={() => void handleForgetMe()}
            disabled={forgetting}
            title="Delete your saved profile facts and stored conversations"
            className="text-xs px-3 py-1.5 rounded-full border border-border text-danger-fg hover:bg-danger-subtle transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-border disabled:opacity-50"
          >
            {forgetting ? "Deleting…" : "Forget what you know about me"}
          </button>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-success animate-pulse" aria-hidden="true" />
            <span className="text-xs text-fg-muted">Sync Ready</span>
          </span>
        </div>
        )}
      </motion.div>

      {isWidget && confirmingForget && (
        <div role="alert" className="border-b border-danger-border bg-danger-subtle px-4 py-3 text-xs text-danger-fg">
          <p className="font-semibold">Delete Dalil memory and stored conversations?</p>
          <p className="mt-1 text-fg-muted">This cannot be undone.</p>
          <div className="mt-2 flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setConfirmingForget(false)}>
              Cancel
            </Button>
            <Button variant="danger" size="sm" loading={forgetting} onClick={() => void handleForgetMe(true)}>
              Delete memory
            </Button>
          </div>
        </div>
      )}

      {memoryNotice && (
        <div
          role="status"
          className={`${isWidget ? "px-4" : "px-8"} py-2 text-xs text-brand-fg bg-canvas-subtle border-b border-border`}
        >
          {memoryNotice}
        </div>
      )}

      {/* Messages Wrapper */}
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.1 }}
        className={`min-h-0 flex-1 overflow-y-auto ${isWidget ? "px-3 py-4" : "px-4 py-6 sm:px-8"}`}
      >
        <MessageList
          messages={messages}
          isTyping={isTyping}
          userInitials={userInitials}
          compact={isWidget}
        />
      </motion.section>

      {/* Inputs Wrapper */}
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15, ease: "easeOut" }}
        className={`border-t border-border bg-surface ${isWidget ? "px-3 py-3" : "px-4 py-4 sm:px-8"}`}
      >
        {explanationContext && (
          <div
            data-testid="explanation-context-card"
            className="mb-3 overflow-hidden rounded-xl border border-brand-border bg-[linear-gradient(135deg,var(--color-brand-subtle),var(--color-surface))] shadow-e1"
          >
            <div className="flex items-start gap-3 px-3 py-2.5">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-fg-on-brand shadow-e1">
                <Sparkles size={15} aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-bold uppercase tracking-wider text-brand-fg">
                  Evidence attached for this question
                </p>
                <p className="mt-0.5 truncate text-sm font-semibold text-fg">
                  {explanationContext.title}
                </p>
                <p className="mt-0.5 text-xs text-fg-muted">
                  {explanationContext.facts.length} evidence detail
                  {explanationContext.facts.length === 1 ? "" : "s"} · removed
                  after you send
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                leadingIcon={X}
                aria-label={`Remove explanation context for ${explanationContext.title}`}
                onClick={onClearExplanationContext}
                className="h-8 w-8 rounded-full"
              />
            </div>
          </div>
        )}
        {profileStatus === "error" && (
          <Alert
            tone="danger"
            title="Couldn't load your profile"
            className="mb-3"
            actions={
              <Button variant="secondary" size="sm" leadingIcon={RotateCcw} onClick={retryProfile}>
                Try again
              </Button>
            }
          >
            {profileError ??
              "Chat will keep using a placeholder identity until this is retried."}
          </Alert>
        )}
        <ChatInput
          onSendMessage={handleSendMessage}
          value={composerDraft}
          onValueChange={setComposerDraft}
          focusRequestKey={focusRequestKey}
          showPracticeShortcuts={!isWidget}
          disabled={identityLoading}
          sending={isSending}
        />
        <div className="text-center text-[11px] text-fg-subtle mt-2">
          Dalil can make mistakes. Verify university requirements before applying.
        </div>
      </motion.section>
    </div>
  );
}
