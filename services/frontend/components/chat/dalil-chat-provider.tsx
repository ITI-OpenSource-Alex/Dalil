"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import ChatWidget from "./chat-widget";
import type { ExplanationContext } from "@/lib/explanation-context";

interface OpenWithPromptOptions {
  /** The control that opened Dalil, used for focus restoration when possible. */
  invoker?: HTMLElement | null;
}

interface DalilChatContextValue {
  open: boolean;
  openChat: (options?: OpenWithPromptOptions) => void;
  closeChat: () => void;
  toggleChat: () => void;
  openWithPrompt: (prompt: string, options?: OpenWithPromptOptions) => void;
  openWithExplanation: (
    prompt: string,
    context: ExplanationContext,
    options?: OpenWithPromptOptions,
  ) => void;
}

const DalilChatContext = createContext<DalilChatContextValue | null>(null);

/**
 * Routes where the floating assistant must not appear.
 *
 * The active paper is the only suppressed route. The exam picker and results
 * pages keep Dalil: the former has no protected submit control, and the latter
 * contains explicit "Ask Dalil" score-explanation actions.
 */
function isActiveExamPath(pathname: string | null): boolean {
  return (
    pathname === "/exam/shell" ||
    pathname?.startsWith("/exam/shell/") === true
  );
}

export function DalilChatProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const inActiveExam = isActiveExamPath(pathname);
  const [open, setOpen] = useState(false);
  const [activated, setActivated] = useState(false);
  const [draft, setDraft] = useState("");
  const [explanationContext, setExplanationContext] =
    useState<ExplanationContext | null>(null);
  const [focusRequestKey, setFocusRequestKey] = useState(0);
  const [unread, setUnread] = useState(false);
  const [busy, setBusy] = useState(false);
  const invokerRef = useRef<HTMLElement | null>(null);

  // If the user starts an exam while the panel is open, unmounting the widget
  // is not enough: leaving the exam would resurrect the old open panel. Close
  // it on entry while preserving any unfinished draft for later.
  useEffect(() => {
    if (!inActiveExam) return;
    setOpen(false);
    setUnread(false);
    invokerRef.current = null;
  }, [inActiveExam]);

  const requestComposerFocus = useCallback(() => {
    setFocusRequestKey((value) => value + 1);
  }, []);

  const openChat = useCallback(
    (options?: OpenWithPromptOptions) => {
      invokerRef.current = options?.invoker ?? null;
      setActivated(true);
      setOpen(true);
      setUnread(false);
      requestComposerFocus();
    },
    [requestComposerFocus],
  );

  const closeChat = useCallback(() => setOpen(false), []);

  const toggleChat = useCallback(() => {
    setOpen((current) => {
      const next = !current;
      if (next) {
        setActivated(true);
        setUnread(false);
        requestComposerFocus();
      }
      return next;
    });
  }, [requestComposerFocus]);

  const openWithPrompt = useCallback(
    (prompt: string, options?: OpenWithPromptOptions) => {
      const contextualPrompt = prompt.trim();
      if (!contextualPrompt) {
        openChat(options);
        return;
      }

      invokerRef.current = options?.invoker ?? null;
      setActivated(true);
      setExplanationContext(null);
      setDraft((current) => {
        const existing = current.trim();
        if (!existing) return contextualPrompt;
        if (existing.includes(contextualPrompt)) return current;
        // Never destroy something the user has already typed. Context from a
        // second component is still ordinary editable chat text.
        return `${current.trimEnd()}\n\n${contextualPrompt}`;
      });
      setOpen(true);
      setUnread(false);
      requestComposerFocus();
    },
    [openChat, requestComposerFocus],
  );

  const openWithExplanation = useCallback(
    (
      prompt: string,
      context: ExplanationContext,
      options?: OpenWithPromptOptions,
    ) => {
      invokerRef.current = options?.invoker ?? null;
      setActivated(true);
      setExplanationContext(context);
      setDraft((current) => {
        const contextualPrompt = prompt.trim();
        const existing = current.trim();
        if (!existing || existing === contextualPrompt) return contextualPrompt;
        if (existing.includes(contextualPrompt)) return current;
        // A contextual action must never erase an unfinished general question.
        // Both parts remain editable, while the visible card makes it clear
        // which evidence bundle will be attached to this one turn.
        return `${current.trimEnd()}\n\n${contextualPrompt}`;
      });
      setOpen(true);
      setUnread(false);
      requestComposerFocus();
    },
    [requestComposerFocus],
  );

  const value = useMemo<DalilChatContextValue>(
    () => ({
      open,
      openChat,
      closeChat,
      toggleChat,
      openWithPrompt,
      openWithExplanation,
    }),
    [
      open,
      openChat,
      closeChat,
      toggleChat,
      openWithPrompt,
      openWithExplanation,
    ],
  );

  return (
    <DalilChatContext.Provider value={value}>
      {children}
      {/*
        The floating widget is suppressed inside the exam shell, for two
        independent reasons, either of which alone would justify it.

        It physically breaks the exam. The pill is fixed bottom-right, which is
        exactly where the Reading and Listening submit buttons sit, and it
        intercepts their pointer events -- a candidate cannot submit. Three
        Reading specs and two Listening specs timed out clicking a button that
        Playwright reported as visible, enabled and covered.

        It also should not be offered there. Everything else about the exam is
        built to protect the simulation: non-seekable audio, one-pass Listening,
        server-authoritative timers, a heartbeat. An always-available AI
        assistant floating over a timed IELTS paper contradicts all of it, and
        nobody chose that -- it arrived because the widget mounts for the whole
        (app) route group.

        The CONTEXT stays mounted either way, so useDalilChat() still resolves
        for anything inside the shell that calls it; only the floating UI goes.
      */}
      {!inActiveExam && (
        <ChatWidget
          open={open}
          activated={activated}
          onOpenChange={(next) => {
            setOpen(next);
            if (next) {
              setActivated(true);
              setUnread(false);
              requestComposerFocus();
            }
          }}
          draft={draft}
          onDraftChange={setDraft}
          explanationContext={explanationContext}
          onClearExplanationContext={() => setExplanationContext(null)}
          focusRequestKey={focusRequestKey}
          busy={busy}
          unread={unread}
          onBusyChange={setBusy}
          onResponseComplete={() => {
            if (!open) setUnread(true);
          }}
          onCloseAutoFocus={(fallback) => {
            const invoker = invokerRef.current;
            invokerRef.current = null;
            if (invoker?.isConnected) invoker.focus();
            else fallback?.focus();
          }}
        />
      )}
    </DalilChatContext.Provider>
  );
}

export function useDalilChat(): DalilChatContextValue {
  const context = useOptionalDalilChat();
  if (!context) {
    throw new Error("useDalilChat must be used inside DalilChatProvider");
  }
  return context;
}

/** Lets reusable result components omit their affordance outside the app shell. */
export function useOptionalDalilChat(): DalilChatContextValue | null {
  return useContext(DalilChatContext);
}
