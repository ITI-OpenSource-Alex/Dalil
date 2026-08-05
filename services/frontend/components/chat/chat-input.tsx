"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, PenSquare, Send } from "lucide-react";

interface ChatInputProps {
  onSendMessage: (text: string) => void;
  onOpenSpeaking: () => void;
  onOpenWriting: () => void;
  /**
   * Which practice mode, if any, currently owns the session — the single
   * source of truth computed in chat-shell.tsx. Whichever mode is active
   * disables the *other* mode's toolbar button, rather than letting the
   * click open a second, conflicting session.
   */
  activePractice: "speaking" | "writing" | null;
  /**
   * True while the real user identity (useCurrentUser) hasn't resolved yet.
   * Disables Send/Speaking/Writing so a message can't go out carrying the
   * CURRENT_USER_ID fallback instead of the logged-in user's real id.
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
  onOpenSpeaking,
  onOpenWriting,
  activePractice,
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

  const writingLocked = activePractice === "speaking" || locked;
  const speakingLocked = activePractice === "writing" || locked;

  return (
    <div className="max-w-4xl mx-auto">
      <motion.div
        layout
        className="relative flex items-end gap-3 bg-white border border-[#D5DDD6] rounded-xl p-2.5 focus-within:ring-2 focus-within:ring-[#0E3D23]/10 focus-within:border-[#0E3D23]"
      >
        <textarea
          data-testid="chat-input"
          ref={textareaRef}
          rows={1}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={sending ? "Waiting for a reply…" : "Ask GOA anything..."}
          className="flex-1 resize-none bg-transparent py-1 px-1 text-sm outline-none placeholder-[#899C8B] text-[#1D291E] max-h-40 min-h-6"
        />

        {/* Writing Practice */}
        <motion.button
          whileTap={writingLocked ? undefined : { scale: 0.92 }}
          onClick={onOpenWriting}
          disabled={writingLocked}
          aria-disabled={writingLocked}
          className="p-2 hover:bg-[#F2F5F1] rounded-lg text-[#526053] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
          title={
            writingLocked
              ? "Finish the current Speaking session before starting Writing Practice."
              : "Writing Practice"
          }
        >
          <PenSquare size={19} />
        </motion.button>

        {/* Speaking */}
        <motion.button
          whileTap={speakingLocked ? undefined : { scale: 0.92 }}
          onClick={onOpenSpeaking}
          disabled={speakingLocked}
          aria-disabled={speakingLocked}
          className="p-2 hover:bg-[#F2F5F1] rounded-lg text-[#526053] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
          title={
            speakingLocked
              ? "Finish the current Writing session before starting Speaking Practice."
              : "Speaking Practice"
          }
        >
          <Mic size={19} />
        </motion.button>

        {/* Send */}
        <motion.button
          data-testid="send-message-button"
          whileTap={{ scale: 0.92 }}
          onClick={handleSubmit}
          disabled={!inputText.trim() || locked}
          aria-busy={sending || undefined}
          title={sending ? "Waiting for the current reply to finish" : "Send"}
          className="p-2 bg-[#0E3D23] text-white rounded-lg hover:bg-[#0A2E1A] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send size={18} />
        </motion.button>
      </motion.div>
    </div>
  );
}
