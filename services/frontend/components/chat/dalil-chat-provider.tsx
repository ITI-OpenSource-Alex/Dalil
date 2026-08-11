"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import ChatWidget from "./chat-widget";

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
}

const DalilChatContext = createContext<DalilChatContextValue | null>(null);

export function DalilChatProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [activated, setActivated] = useState(false);
  const [draft, setDraft] = useState("");
  const [focusRequestKey, setFocusRequestKey] = useState(0);
  const [unread, setUnread] = useState(false);
  const [busy, setBusy] = useState(false);
  const invokerRef = useRef<HTMLElement | null>(null);

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

  const value = useMemo<DalilChatContextValue>(
    () => ({ open, openChat, closeChat, toggleChat, openWithPrompt }),
    [open, openChat, closeChat, toggleChat, openWithPrompt],
  );

  return (
    <DalilChatContext.Provider value={value}>
      {children}
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
    </DalilChatContext.Provider>
  );
}

export function useDalilChat(): DalilChatContextValue {
  const context = useContext(DalilChatContext);
  if (!context) {
    throw new Error("useDalilChat must be used inside DalilChatProvider");
  }
  return context;
}
