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
}

export default function ChatInput({
  onSendMessage,
  onOpenSpeaking,
  onOpenWriting,
  activePractice,
  disabled = false,
}: ChatInputProps) {
  const [inputText, setInputText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!textareaRef.current) return;

    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(
      textareaRef.current.scrollHeight,
      160,
    )}px`;
  }, [inputText]);

  const handleSubmit = () => {
    if (!inputText.trim() || disabled) return;

    onSendMessage(inputText);
    setInputText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const writingLocked = activePractice === "speaking" || disabled;
  const speakingLocked = activePractice === "writing" || disabled;

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
          placeholder="Ask GOA anything..."
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
          disabled={!inputText.trim() || disabled}
          className="p-2 bg-[#0E3D23] text-white rounded-lg hover:bg-[#0A2E1A] disabled:opacity-50"
        >
          <Send size={18} />
        </motion.button>
      </motion.div>
    </div>
  );
}
