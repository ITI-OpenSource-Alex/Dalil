"use client";
import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Message, Opportunity, EvaluationResult } from "./chat-shell";
import { GraduationCap, MapPin, Calendar, Award } from "lucide-react";
import TypingIndicator from "./typing-indicator";
import MessageBubble from "./message-bubble";
import SourcesFootnote from "./sources-footnote";

interface MessageListProps {
  messages: Message[];
  isTyping: boolean;
}

export default function MessageList({ messages, isTyping }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <AnimatePresence initial={false}>
        {messages.map((msg) => {
          const isUser = msg.role === "user";
          return (
            <motion.div
              key={msg.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className={`flex gap-4 ${isUser ? "justify-end" : "justify-start"}`}
            >
              <MessageBubble
                role={msg.role}
                content={msg.content}
                intent={msg.intent}
                isStreaming={msg.isStreaming}
              />

              {msg.sources && msg.sources.length > 0 && (
                <SourcesFootnote sources={msg.sources} />
              )}

              {msg.opportunities && msg.opportunities.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                  {msg.opportunities.map((opp, idx) => (
                    <OpportunityCard key={idx} opp={opp} index={idx} />
                  ))}
                </div>
              )}

              {msg.evaluation && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{
                    duration: 0.4,
                    delay: 0.1,
                    ease: "easeOut",
                  }}
                  className="mt-2"
                >
                  <EvaluationReport evaluation={msg.evaluation} />
                </motion.div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Typing Indicator */}
      <AnimatePresence>{isTyping && <TypingIndicator />}</AnimatePresence>

      <div ref={endRef} />
    </div>
  );
}

// Opportunity Matching Card UI Component
function OpportunityCard({
  opp,
  index = 0,
}: {
  opp: Opportunity;
  index?: number;
}) {
  const confidencePercent = Math.round(opp.confidence * 100);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.06, ease: "easeOut" }}
      className="bg-white border border-[#E4EAE4] rounded-xl p-4 shadow-sm flex flex-col justify-between"
    >
      <div>
        <div className="flex justify-between items-start gap-2">
          <h4 className="font-semibold text-sm text-[#0D3820] line-clamp-1">
            {opp.programName}
          </h4>
          <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md shrink-0">
            {confidencePercent}% Match
          </span>
        </div>
        <div className="space-y-1.5 mt-3 text-xs text-[#526053]">
          <p className="flex items-center gap-1.5">
            <GraduationCap size={13} className="text-[#899C8B]" />
            <span className="line-clamp-1">{opp.university}</span>
          </p>
          <p className="flex items-center gap-1.5">
            <MapPin size={13} className="text-[#899C8B]" />
            <span>{opp.country}</span>
          </p>
          <p className="flex items-center gap-1.5">
            <Calendar size={13} className="text-[#899C8B]" />
            <span>Deadline: {opp.deadline}</span>
          </p>
        </div>
      </div>
      {/* Confidence Indicator Bar */}
      <div className="mt-4">
        <div className="w-full bg-[#F0F3EF] h-1.5 rounded-full overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${confidencePercent}%` }}
            transition={{
              duration: 0.6,
              delay: 0.2 + index * 0.06,
              ease: "easeOut",
            }}
            className="bg-emerald-600 h-full rounded-full"
          />
        </div>
      </div>
    </motion.div>
  );
}

// Speaking Practice Evaluation UI Component
function EvaluationReport({ evaluation }: { evaluation: EvaluationResult }) {
  const criteriaList = [
    { label: "Fluency & Coherence", score: evaluation.criteria.fluency },
    { label: "Lexical Resource", score: evaluation.criteria.lexical },
    { label: "Grammatical Range", score: evaluation.criteria.grammar },
    {
      label: "Pronunciation Accuracy",
      score: evaluation.criteria.pronunciation,
    },
  ];
  return (
    <div className="bg-white border border-emerald-100 rounded-xl p-4 shadow-sm max-w-md">
      <div className="flex items-center gap-2 mb-3">
        <Award className="text-emerald-600" size={18} />
        <h4 className="font-bold text-sm text-[#0D3820]">
          IELTS Speaking Band Score
        </h4>
      </div>
      {/* Overall Score Badge */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, delay: 0.15 }}
        className="flex items-center gap-3 bg-emerald-50/50 p-2.5 rounded-lg mb-4"
      >
        <div className="w-12 h-12 rounded-full bg-emerald-600 text-white flex items-center justify-center font-extrabold text-lg">
          {evaluation.overallScore}
        </div>
        <div>
          <p className="text-xs font-semibold text-[#0E3D23]">
            Estimated Overall Band
          </p>
          <p className="text-[10px] text-[#526053]">
            Based on criterion rubrics
          </p>
        </div>
      </motion.div>
      {/* Criteria Sliders */}
      <div className="space-y-2 mb-3">
        {criteriaList.map((item, idx) => (
          <div key={idx}>
            <div className="flex justify-between text-[11px] font-medium text-[#1D291E]">
              <span>{item.label}</span>
              <span className="font-bold">Band {item.score}</span>
            </div>
            <div className="w-full bg-[#F0F3EF] h-1 rounded-full overflow-hidden mt-1">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${(item.score / 9) * 100}%` }}
                transition={{
                  duration: 0.5,
                  delay: 0.2 + idx * 0.08,
                  ease: "easeOut",
                }}
                className="bg-emerald-500 h-full rounded-full"
              />
            </div>
          </div>
        ))}
      </div>
      <div className="border-t border-[#EDF1EE] pt-2 mt-2">
        <p className="text-[11px] font-medium text-[#526053]">
          Expert Feedback:
        </p>
        <p className="text-[11px] text-[#526053] leading-relaxed mt-1 italic">
          "{evaluation.feedback}"
        </p>
      </div>
    </div>
  );
}
