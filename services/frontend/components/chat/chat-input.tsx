"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Mic, PenSquare, Send } from "lucide-react";

interface ChatInputProps {
  onSendMessage: (text: string) => void;
  /**
   * True while the real user identity (useCurrentUser) hasn't resolved yet.
   * Disables Send so a message can't go out carrying the CURRENT_USER_ID
   * fallback instead of the logged-in user's real id.
   */
  disabled?: boolean;
  /**
   * True while a reply is streaming. The shell already refuses a second
   * concurrent turn, but a Send button that silently does nothing is a worse
   * answer than one that visibly cannot be pressed — and pressing it twice is
   * how the duplicate-reply bug was reproduced in the first place.
   */
  sending?: boolean;
}

export default function ChatInput({
  onSendMessage,
  disabled = false,
  sending = false,
}: ChatInputProps) {
  const [inputText, setInputText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const locked = disabled || sending;

  useEffect(() => {
    if (!textareaRef.current) return;

    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(
      textareaRef.current.scrollHeight,
      160,
    )}px`;
  }, [inputText]);

  const handleSubmit = () => {
    if (!inputText.trim() || locked) return;

    onSendMessage(inputText);
    setInputText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <motion.div
        layout
        className="relative flex items-end gap-3 bg-surface border border-border-strong rounded-xl p-2.5 focus-within:ring-2 focus-within:ring-brand-muted focus-within:border-brand"
      >
        <textarea
          data-testid="chat-input"
          ref={textareaRef}
          rows={1}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={sending ? "Waiting for a reply…" : "Ask GOA anything..."}
          className="flex-1 resize-none bg-transparent py-1 px-1 text-sm outline-none placeholder:text-fg-subtle text-fg max-h-40 min-h-6"
        />

        {/* Writing Practice now has its own page (Phase D) -- these are
            deep links into it, not an inline toggle. Chat is a secondary
            entry point, not the only one. */}
        <Link
          href="/practice/writing"
          className="p-2 hover:bg-canvas-subtle rounded-lg text-fg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
          title="Writing Practice"
          aria-label="Writing Practice"
        >
          <PenSquare size={19} />
        </Link>

        {/* Speaking Practice */}
        <Link
          href="/practice/speaking"
          className="p-2 hover:bg-canvas-subtle rounded-lg text-fg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
          title="Speaking Practice"
          aria-label="Speaking Practice"
        >
          <Mic size={19} />
        </Link>

        {/* Send */}
        <motion.button
          data-testid="send-message-button"
          whileTap={{ scale: 0.92 }}
          onClick={handleSubmit}
          disabled={!inputText.trim() || locked}
          aria-busy={sending || undefined}
          title={sending ? "Waiting for the current reply to finish" : "Send"}
          aria-label={sending ? "Waiting for the current reply to finish" : "Send"}
          className="p-2 bg-brand text-fg-on-brand rounded-lg hover:bg-brand-hover disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
        >
          <Send size={18} />
        </motion.button>
      </motion.div>
    </div>
  );
}
