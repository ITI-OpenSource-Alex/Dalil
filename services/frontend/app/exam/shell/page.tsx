"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useExamTimer } from "@/app/hooks/useExamTimer";
import { ExamType, SkillArea, ExamStatus } from "@/app/types/exam";

export default function ExamShell() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session") || "";

  const [examConfig, setExamConfig] = useState<{
    type: ExamType;
    skill: SkillArea;
  } | null>(null);
  const [status, setStatus] = useState<ExamStatus>("in_progress");
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [writingInput, setWritingInput] = useState({ task1: "", task2: "" });
  const [mounted, setMounted] = useState(false);

  // Safety checks & Hydration restoration
  useEffect(() => {
    const saved = sessionStorage.getItem("active_exam_session");
    if (!saved) {
      router.push("/exam");
      return;
    }
    const parsed = JSON.parse(saved);
    setExamConfig({ type: parsed.examType, skill: parsed.skillArea });
  }, [router]);

  // Trigger entrance animation once the exam config is ready
  useEffect(() => {
    if (examConfig) {
      const raf = requestAnimationFrame(() => setMounted(true));
      return () => cancelAnimationFrame(raf);
    }
  }, [examConfig]);

  // Combined programmatic state logic submit system
  const executeSubmission = async () => {
    setShowSubmitModal(false);
    if (examConfig?.skill === "Speaking") {
      setStatus("evaluating");
      // Simulate Speaking State Machine Evolution
      setTimeout(() => setStatus("part1_done"), 2000);
      setTimeout(() => setStatus("part2_done"), 4000);
      setTimeout(() => setStatus("part3_done"), 6000);
      setTimeout(() => {
        router.push(`/exam/results?session=${sessionId}&skill=Speaking`);
      }, 9000);
    } else {
      router.push(
        `/exam/results?session=${sessionId}&skill=${examConfig?.skill}`,
      );
    }
  };

  const { formatTime, isCritical } = useExamTimer(
    1800,
    sessionId,
    executeSubmission,
  );

  if (!examConfig)
    return (
      <div className="min-h-screen bg-linear-to-br from-emerald-50 via-white to-yellow-50 p-8 font-mono">
        Loading active profile session context...
      </div>
    );

  return (
    <div className="fixed inset-0 bg-linear-to-br from-emerald-50 via-white to-yellow-50 text-black flex flex-col z-50 select-none overflow-hidden min-w-3xl">
      {/* Dynamic Full-Screen Responsive Blocker */}
      <div className="md:hidden fixed inset-0 bg-black text-white z-100 flex flex-col justify-center items-center p-6 text-center">
        <p className="text-xl font-bold mb-2">EXAM MODE LOCKED</p>
        <p className="text-sm text-neutral-400">
          Desktop or Tablet interface orientation (greater than or equal to
          768px screen resolution boundary width) is required to ensure testing
          compatibility standards.
        </p>
      </div>

      <div
        className={`flex flex-col flex-1 min-h-0 transition-all duration-700 ease-out ${
          mounted ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-3"
        }`}
      >
        {/* Top persistent control panel bar */}
        <header className="h-16 border-b border-gray-200 px-6 flex justify-between items-center bg-white/70 backdrop-blur-sm shrink-0">
          <div className="flex items-center gap-3">
            <span className="font-bold text-lg uppercase tracking-tight text-black">
              {examConfig.skill} Module
            </span>
            <span className="bg-yellow-50 border border-gray-300 px-2.5 py-0.5 text-xs font-bold rounded-md text-gray-700">
              {examConfig.type}
            </span>
          </div>

          <div className="flex items-center gap-4">
            <div
              className={`font-mono text-lg font-bold px-3 py-1 rounded-lg border transition-colors duration-300 ${
                isCritical
                  ? "bg-red-50 text-red-600 border-red-300 animate-pulse"
                  : "bg-yellow-50 text-black border-gray-300"
              }`}
            >
              {formatTime()}
            </div>
            <button
              onClick={() => setShowSubmitModal(true)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 rounded-lg font-bold shadow-sm transition-colors duration-200"
            >
              SUBMIT EXAM
            </button>
          </div>
        </header>

        {/* Main Workspace Frame */}
        <main className="flex-1 overflow-auto p-6">
          {examConfig.skill === "Writing" && (
            <div className="grid grid-cols-2 gap-6 h-full min-h-125">
              {/* Task 1 Panel Layout */}
              <div className="border border-gray-200 rounded-xl p-5 flex flex-col bg-white shadow-sm">
                <div className="flex justify-between items-center mb-3 border-b border-gray-100 pb-2">
                  <h4 className="font-bold text-black">
                    TASK 1 (Report/Letter)
                  </h4>
                  {status === "task1_evaluating" && (
                    <span className="text-xs bg-black text-white px-2 py-0.5 rounded animate-pulse">
                      Processing Analysis...
                    </span>
                  )}
                  {status !== "in_progress" && status !== "task1_submitted" && (
                    <span className="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded font-medium">
                      Evaluation Buffered
                    </span>
                  )}
                </div>
                <textarea
                  value={writingInput.task1}
                  onChange={(e) =>
                    setWritingInput({ ...writingInput, task1: e.target.value })
                  }
                  disabled={status !== "in_progress"}
                  className="w-full flex-1 p-3 bg-yellow-50 border border-gray-300 rounded-lg text-black font-mono text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition resize-none disabled:opacity-60"
                  placeholder="Compose Task 1 response here..."
                />
                {status === "in_progress" && (
                  <button
                    onClick={() => setStatus("task1_evaluating")}
                    className="mt-3 bg-black hover:bg-neutral-800 text-white py-2 rounded-lg font-bold text-sm transition"
                  >
                    Lock & Submit Task 1
                  </button>
                )}
              </div>

              {/* Task 2 Panel Layout */}
              <div className="border border-gray-200 rounded-xl p-5 flex flex-col bg-white shadow-sm">
                <h4 className="font-bold mb-3 border-b border-gray-100 pb-2 text-black">
                  TASK 2 (Extended Essay Format)
                </h4>
                <textarea
                  value={writingInput.task2}
                  onChange={(e) =>
                    setWritingInput({ ...writingInput, task2: e.target.value })
                  }
                  className="w-full flex-1 p-3 bg-yellow-50 border border-gray-300 rounded-lg text-black font-mono text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition resize-none"
                  placeholder="Compose Task 2 argument variant response here..."
                />
              </div>
            </div>
          )}

          {examConfig.skill !== "Writing" && (
            <div className="bg-white border border-gray-200 rounded-xl p-8 max-w-3xl mx-auto my-8 shadow-sm">
              <p className="text-sm text-gray-500 mb-4">
                Standard standardized platform layout containing questions for
                candidate simulation review.
              </p>
              <div className="h-64 border border-dashed border-gray-300 rounded-lg bg-yellow-50/50 flex items-center justify-center text-gray-400 font-medium">
                Interactive Simulation Layer Frame
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Speaking Active Machine Full-Screen Overlay View blocker */}
      {status === "evaluating" && (
        <div className="fixed inset-0 bg-black/95 text-white z-200 flex flex-col justify-center items-center">
          <div className="w-24 h-12 flex items-end justify-between gap-1 mb-6">
            <div
              className="w-2 bg-white animate-[bounce_1s_infinite_100ms]"
              style={{ height: "40%" }}
            ></div>
            <div
              className="w-2 bg-emerald-500 animate-[bounce_1s_infinite_200ms]"
              style={{ height: "80%" }}
            ></div>
            <div
              className="w-2 bg-white animate-[bounce_1s_infinite_300ms]"
              style={{ height: "60%" }}
            ></div>
            <div
              className="w-2 bg-emerald-500 animate-[bounce_1s_infinite_400ms]"
              style={{ height: "100%" }}
            ></div>
          </div>
          <p className="text-xl font-mono tracking-widest text-center uppercase animate-pulse">
            Analysing your performance across all 3 parts...
          </p>
          <span className="text-xs text-neutral-400 mt-2 font-mono">
            Evaluating linguistic metrics & fluency algorithms
          </span>
        </div>
      )}

      {/* Modal Prompt Intercept Window */}
      {showSubmitModal && (
        <div className="fixed inset-0 bg-black/50 z-150 flex items-center justify-center p-4 backdrop-blur-xs">
          <div className="bg-white border border-gray-200 p-6 max-w-md w-full rounded-xl shadow-lg animate-[fadeInScale_0.25s_ease-out]">
            <h3 className="text-lg font-bold text-black mb-1">
              Conclude Examination Session?
            </h3>
            <p className="text-sm text-gray-500 mb-6">
              Confirm submission sequence. Answers collected up to this
              benchmark run will undergo final linguistic analysis.
            </p>
            <div className="flex justify-end gap-3 font-semibold text-sm">
              <button
                onClick={() => setShowSubmitModal(false)}
                className="border border-gray-300 rounded-lg px-4 py-2 text-gray-700 hover:bg-neutral-50 transition"
              >
                Cancel
              </button>
              <button
                onClick={executeSubmission}
                className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-4 py-2 shadow-sm transition"
              >
                Submit and Exit
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes fadeInScale {
          from {
            opacity: 0;
            transform: scale(0.96);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }
      `}</style>
    </div>
  );
}
