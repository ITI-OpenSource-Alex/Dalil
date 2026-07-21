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

export type Opportunity = {
  programName: string;
  university: string;
  country: string;
  deadline: string;
  confidence: number; // 0 to 1
};

export type EvaluationResult = {
  overallScore: number;
  criteria: {
    fluency: number;
    lexical: number;
    grammar: number;
    pronunciation: number;
  };
  feedback: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  intent?: string;
  confidence?: number;
  opportunities?: Opportunity[];
  evaluation?: EvaluationResult;
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
  const [sessionId] = useState("session-lina-123"); // Hardcoded or dynamic
  const [userId] = useState("user-lina");
  const speakingQuestion = {
    prompt: "Describe a memorable journey you have taken.",
    type: "part2",
  };

  const recorderRef = useRef<AudioRecorder | null>(null);
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

  // Load session history on mount
  useEffect(() => {
    async function loadHistory() {
      try {
        const res = await fetch(`/api/chat/sessions/${sessionId}/history`);
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
        speakingSocket.current?.close();

        speakingSocket.current = new SpeakingWebSocket({
          wsUrl: event.wsUrl,
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

          onStateChange: (socketState) => {
            switch (socketState) {
              case "connecting":
                setSpeakingState("idle");
                break;

              case "connected":
                setSpeakingState("listening");

                recorderRef.current = new AudioRecorder({
                  onAudioChunk: (chunk) => {
                    speakingSocket.current?.sendAudio(chunk);
                  },
                });

                recorderRef.current.start();

                break;
              case "recording":
                setSpeakingState("listening");
                break;

              case "processing":
                setSpeakingState("transcribing");
                break;

              case "done":
                setSpeakingState("done");
                break;

              case "error":
                setSpeakingState("idle");
                break;
            }
          },

          onEvaluation: (evaluation) => {
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
                  criteria: {
                    fluency: evaluation.dimensions?.fluency?.band ?? 0,
                    lexical: evaluation.dimensions?.lexical_resource?.band ?? 0,
                    grammar: evaluation.dimensions?.grammar?.band ?? 0,
                    pronunciation:
                      evaluation.dimensions?.pronunciation?.band ?? 0,
                  },
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
      const response = await fetch("/api/chat", {
        method: "POST",
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
    } catch (error) {
      console.error(error);

      setIsTyping(false);

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

    await handleSendMessage(essay);
  };

  const startSpeaking = async () => {
    setSpeakingOpen(true);
    setSpeakingState("listening");
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        await navigator.mediaDevices.getUserMedia({ audio: true });
      }
    } catch (e) {
      console.error("Mic permission error:", e);
    }
  };


  const stopSpeaking = () => {
    recorderRef.current?.stop();

    speakingSocket.current?.finishRecording();
  };

  useEffect(() => {
    return () => {
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
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-[#526053]">Sync Ready</span>
        </div>
      </motion.div>

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
          onStart={startSpeaking}
          onStop={stopSpeaking}
          onClose={() => {
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
