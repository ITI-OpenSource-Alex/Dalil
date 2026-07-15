"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, PenSquare, Send } from "lucide-react";

interface ChatInputProps {
  onSendMessage: (text: string) => void;
  onOpenSpeaking: () => void;
  onOpenWriting: () => void;
}

export default function ChatInput({
  onSendMessage,
  onOpenSpeaking,
  onOpenWriting,
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
    if (!inputText.trim()) return;

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
          whileTap={{ scale: 0.92 }}
          onClick={onOpenWriting}
          className="p-2 hover:bg-[#F2F5F1] rounded-lg text-[#526053]"
          title="Writing Practice"
        >
          <PenSquare size={19} />
        </motion.button>

        {/* Speaking */}
        <motion.button
          whileTap={{ scale: 0.92 }}
          onClick={onOpenSpeaking}
          className="p-2 hover:bg-[#F2F5F1] rounded-lg text-[#526053]"
          title="Speaking Practice"
        >
          <Mic size={19} />
        </motion.button>

        {/* Send */}
        <motion.button
          data-testid="send-message-button"
          whileTap={{ scale: 0.92 }}
          onClick={handleSubmit}
          disabled={!inputText.trim()}
          className="p-2 bg-[#0E3D23] text-white rounded-lg hover:bg-[#0A2E1A] disabled:opacity-50"
        >
          <Send size={18} />
        </motion.button>
      </motion.div>
    </div>
  );
}
