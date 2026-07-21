"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useExamTimer } from "@/app/hooks/useExamTimer";
import { ExamType, SkillArea, ExamStatus } from "@/app/types/exam";
import { getSession, submitSession } from "@/lib/exam-api";
// import { evaluateEssay } from "@/lib/writing-api";
import type { ExamSessionResponse } from "@/lib/exam-api";
import { Sidebar } from "@/components/ui/sidebar";

export default function ExamShell() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session") || "";

  const [session, setSession] = useState<ExamSessionResponse | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);

  const [examConfig, setExamConfig] = useState<{
    type: ExamType;
    skill: SkillArea;
  } | null>(null);
  const [status, setStatus] = useState<ExamStatus>("in_progress");
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [writingInput, setWritingInput] = useState({ task1: "", task2: "" });
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    async function loadSession() {
      if (!sessionId) {
        router.push("/exam");
        return;
      }

      try {
        const data = await getSession(sessionId);

        setSession(data);

        setExamConfig({
          type: data.exam_type === "academic" ? "Academic" : "General",

          skill: (data.skill_area.charAt(0).toUpperCase() +
            data.skill_area.slice(1)) as SkillArea,
        });
      } catch (err) {
        console.error(err);
        router.push("/exam");
      } finally {
        setLoadingSession(false);
      }
    }

    loadSession();
  }, [sessionId]);

  useEffect(() => {
    if (examConfig) {
      const raf = requestAnimationFrame(() => setMounted(true));
      return () => cancelAnimationFrame(raf);
    }
  }, [examConfig]);

  const executeSubmission = async () => {
    setShowSubmitModal(false);

    try {
      setStatus("evaluating");

      const result = await submitSession(sessionId, {
        task1: writingInput.task1,
        task2: writingInput.task2,
      });

      console.log(result);

      router.push(`/exam/results?session=${sessionId}&skill=Writing`);
    } catch (err) {
      console.error(err);
    }
  };

  const { formattedTime, isCritical } = useExamTimer(
    session?.remaining_time_seconds ?? 0,
    executeSubmission,
  );

  if (loadingSession || !session || !examConfig)
    return (
      <div className="min-h-screen bg-[#fbfbfa] p-8 font-mono text-xs text-gray-500">
        Loading active session...
      </div>
    );

  return (
    <div className="flex h-screen bg-[#fbfbfa] text-gray-900 select-none overflow-hidden min-w-3xl">
      <Sidebar />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Responsive Desktop Enforcement Warning */}
        <div className="md:hidden fixed inset-0 bg-gray-900 text-white z-100 flex flex-col justify-center items-center p-6 text-center">
          <p className="text-xl font-bold mb-2">EXAM MODE LOCKED</p>
          <p className="text-sm text-gray-400">
            Desktop screen resolution required for exam simulation.
          </p>
        </div>

        <div
          className={`flex flex-col flex-1 min-h-0 transition-all duration-700 ease-out ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-3"
          }`}
        >
          {/* Header Bar */}
          <header className="h-16 border-b border-gray-200/80 px-8 flex justify-between items-center bg-white shrink-0">
            <div className="flex items-center gap-3">
              <span className="font-serif text-lg font-bold text-gray-900">
                {examConfig.skill} Module
              </span>
              <span className="bg-[#e2f4ea] text-[#0d4d3a] px-2.5 py-0.5 text-xs font-semibold rounded-full">
                {examConfig.type}
              </span>
            </div>

            <div className="flex items-center gap-4">
              <div
                className={`font-mono text-sm font-semibold px-3 py-1 rounded-full border transition-colors ${
                  isCritical
                    ? "bg-red-50 text-red-600 border-red-300 animate-pulse"
                    : "bg-gray-100 text-gray-800 border-gray-200"
                }`}
              >
                {formattedTime}
              </div>
              <button
                onClick={() => setShowSubmitModal(true)}
                className="bg-[#0d4d3a] hover:bg-[#09382a] text-white px-4 py-1.5 rounded-full text-xs font-semibold transition"
              >
                Submit Exam
              </button>
            </div>
          </header>

          {/* Workspace Area */}
          <main className="flex-1 overflow-auto p-8 bg-[#fbfbfa]">
            {examConfig.skill === "Writing" && (
              <div className="grid grid-cols-2 gap-6 h-full min-h-125">
                {/* Task 1 Panel */}
                <div className="border border-gray-200/80 rounded-2xl p-5 flex flex-col bg-white shadow-2xs">
                  <div className="flex justify-between items-center mb-3 border-b border-gray-100 pb-2">
                    <h4 className="font-serif text-sm font-bold text-gray-900">
                      TASK 1 (Report / Letter)
                    </h4>
                  </div>
                  <div className="mb-4 text-sm whitespace-pre-wrap">
                    {String(session.questions[0].questions[0].prompt)}
                  </div>
                  <textarea
                    value={writingInput.task1}
                    onChange={(e) =>
                      setWritingInput({
                        ...writingInput,
                        task1: e.target.value,
                      })
                    }
                    disabled={status !== "in_progress"}
                    className="w-full flex-1 p-3.5 bg-gray-50/50 border border-gray-200 rounded-xl text-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-[#0d4d3a]/20 focus:border-[#0d4d3a] transition resize-none disabled:opacity-60"
                    placeholder="Compose Task 1 response here..."
                  />
                </div>

                {/* Task 2 Panel */}
                <div className="border border-gray-200/80 rounded-2xl p-5 flex flex-col bg-white shadow-2xs">
                  <h4 className="font-serif text-sm font-bold mb-3 border-b border-gray-100 pb-2 text-gray-900">
                    TASK 2 (Extended Essay)
                  </h4>
                  <div className="mb-4 text-sm whitespace-pre-wrap">
                    {String(session.questions[0].questions[1].prompt)}
                  </div>
                  <textarea
                    value={writingInput.task2}
                    onChange={(e) =>
                      setWritingInput({
                        ...writingInput,
                        task2: e.target.value,
                      })
                    }
                    className="w-full flex-1 p-3.5 bg-gray-50/50 border border-gray-200 rounded-xl text-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-[#0d4d3a]/20 focus:border-[#0d4d3a] transition resize-none"
                    placeholder="Compose Task 2 argument response here..."
                  />
                </div>
              </div>
            )}

            {examConfig.skill !== "Writing" && (
              <div className="bg-white border border-gray-200/80 rounded-2xl p-8 max-w-3xl mx-auto my-8 shadow-2xs">
                <p className="text-xs text-gray-500 mb-4">
                  Standard exam interface containing simulation questions.
                </p>
                <div className="h-64 border border-dashed border-gray-200 rounded-xl bg-gray-50 flex items-center justify-center text-gray-400 text-xs font-medium">
                  Interactive Simulation Workspace
                </div>
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Speaking Overlay View */}
      {status === "evaluating" && (
        <div className="fixed inset-0 bg-gray-950/90 text-white z-200 flex flex-col justify-center items-center">
          <p className="text-lg font-serif tracking-wide text-center uppercase animate-pulse">
            Analyzing performance...
          </p>
        </div>
      )}

      {/* Submit Confirmation Modal */}
      {showSubmitModal && (
        <div className="fixed inset-0 bg-black/40 z-150 flex items-center justify-center p-4 backdrop-blur-xs">
          <div className="bg-white border border-gray-200 p-6 max-w-sm w-full rounded-2xl shadow-xl">
            <h3 className="text-base font-bold text-gray-900 mb-1">
              Submit Examination?
            </h3>
            <p className="text-xs text-gray-500 mb-6">
              Your responses will be evaluated using AI scoring guidelines.
            </p>
            <div className="flex justify-end gap-2 text-xs font-semibold">
              <button
                onClick={() => setShowSubmitModal(false)}
                className="border border-gray-200 rounded-full px-4 py-2 text-gray-600 hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                onClick={executeSubmission}
                className="bg-[#0d4d3a] hover:bg-[#09382a] text-white rounded-full px-4 py-2 transition"
              >
                Submit & Exit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}