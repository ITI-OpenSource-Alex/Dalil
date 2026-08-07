"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useExamTimer } from "@/app/hooks/useExamTimer";
import { ExamType, SkillArea, ExamStatus } from "@/app/types/exam";
import { getSession, sendHeartbeat, submitSession } from "@/lib/exam-api";
import { extractRawQuestions } from "@/lib/reading-api";

// Well inside the backend's 10-minute grace window, so several consecutive
// failures are survivable.
const HEARTBEAT_INTERVAL_MS = 60_000;
// import { evaluateEssay } from "@/lib/writing-api";
import type { ExamSessionResponse } from "@/lib/exam-api";
import { Sidebar } from "@/components/ui/sidebar";
import ReadingExam from "@/components/reading/ReadingExam";
import ListeningExam from "@/components/listening/ListeningExam";
import { storeReadingResult } from "@/lib/reading-result-storage";
import { storeListeningResult } from "@/lib/listening-result-storage";
import type {
  NormalizedReadingQuestion,
  ReadingSubmitResponse,
  RawReadingQuestion,
} from "@/app/types/reading";
import type {
  ListeningSubmitResponse,
  NormalizedListeningQuestion,
} from "@/app/types/listening";

// useSearchParams() opts the page into client-side rendering during
// prerendering, which Next.js requires to be wrapped in a Suspense boundary
// (https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout) —
// otherwise `next build`'s static export of this route fails.
export default function ExamShell() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#fbfbfa] p-8 font-mono text-xs text-gray-500">
          Loading active session...
        </div>
      }
    >
      <ExamShellContent />
    </Suspense>
  );
}

// Listening sessions receive their audio URLs from the start response, not
// from the generic session fetch. The shell falls back to the stored start
// payload when the session object itself does not include audio_urls.
function getListeningAudioUrls(
  session: ExamSessionResponse | null,
  sessionId: string,
): [string, string, string, string] | null {
  const sessionUrls = (session as unknown as { audio_urls?: unknown })
    .audio_urls;
  if (
    Array.isArray(sessionUrls) &&
    sessionUrls.length === 4 &&
    sessionUrls.every((url) => typeof url === "string")
  ) {
    return sessionUrls as [string, string, string, string];
  }

  if (typeof window === "undefined") return null;

  try {
    const storedListeningSession = window.sessionStorage.getItem(
      `listening_start_${sessionId}`,
    );
    if (!storedListeningSession) return null;

    const parsed = JSON.parse(storedListeningSession) as unknown as {
      audio_urls?: unknown;
    };
    const urls = parsed.audio_urls;

    if (
      Array.isArray(urls) &&
      urls.length === 4 &&
      urls.every((url) => typeof url === "string")
    ) {
      return urls as [string, string, string, string];
    }
  } catch {
    return null;
  }

  return null;
}

function ExamShellContent() {
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
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Bumped to trigger ReadingExam's own submit on timer expiry — see
  // ReadingExam's forceSubmitSignal prop for why this can't just reuse
  // executeSubmission below, which is hardcoded to Writing's payload shape.
  const [readingForceSubmit, setReadingForceSubmit] = useState(0);

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

  // Keep the session alive for as long as this page is open.
  //
  // The backend sweeps in-progress sessions that stop reporting and marks them
  // abandoned; submit then returns 403 and the candidate loses the attempt. The
  // heartbeat endpoint existed but no client had ever called it (BUG-054).
  //
  // 60s against a 10-minute grace window means roughly nine consecutive
  // failures before a session is at risk, so a brief network drop costs
  // nothing. One fires immediately so a session is marked live from the moment
  // the exam opens rather than a minute into it.
  //
  // Skill-agnostic by design — Listening keeps this running exactly like
  // every other module, including through its own silence-gap and
  // answer-transfer phases, since none of those change `status`.
  useEffect(() => {
    if (!sessionId || status !== "in_progress") {
      return;
    }

    void sendHeartbeat(sessionId);
    const timer = setInterval(() => {
      void sendHeartbeat(sessionId);
    }, HEARTBEAT_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [sessionId, status]);

  const executeSubmission = async () => {
    setShowSubmitModal(false);
    setSubmitError(null);

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
      setStatus("in_progress");
      setSubmitError("Submission failed. Please try again.");
    }
  };

  const handleReadingSubmitted = (
    result: ReadingSubmitResponse,
    questions: NormalizedReadingQuestion[],
  ) => {
    // No GET-result endpoint exists for Reading — the full per-question
    // breakdown only ever exists as this submit call's own response, so it
    // has to be carried forward rather than re-fetched. See
    // lib/reading-result-storage.ts.
    storeReadingResult(sessionId, { result, questions });
    router.push(`/exam/results?session=${sessionId}&skill=Reading`);
  };

  const handleListeningSubmitted = (
    result: ListeningSubmitResponse,
    questions: NormalizedListeningQuestion[],
  ) => {
    // Same constraint as Reading: no GET-result endpoint, so the submit
    // response is carried forward via storage rather than re-fetched.
    storeListeningResult(sessionId, { result, questions });
    router.push(`/exam/results?session=${sessionId}&skill=Listening`);
  };

  const handleTimeUp = () => {
    if (!examConfig) return;

    switch (examConfig?.skill) {
      case "Reading":
        // useExamTimer is called below with session?.remaining_time_seconds ?? 0
        // — before the session finishes loading, that's 0, which makes the
        // timer fire an immediate (spurious) time-up on mount, before
        // examConfig exists. Ignoring that null-session case here is required
        // for Reading/Listening (and doesn't change Writing's real-timeout
        // behavior, which only ever fires once examConfig is already set).
        setReadingForceSubmit((n) => n + 1);
        break;

      case "Listening":
        // ListeningExam owns its own submission flow via the mandated
        // 10-minute answer-transfer countdown (see its TRANSFER_TICK /
        // handleSubmit) and already disables its own Submit button once that
        // window elapses. Calling executeSubmission() here would fire
        // Writing's task1/task2 payload shape against a Listening session and
        // fight with the transfer window ListeningExam is already managing —
        // so this is intentionally a no-op. The shell's outer timer is not
        // the authority on when a Listening attempt ends.
        return;

      case "Writing":
        executeSubmission();
        break;

      case "Speaking":
        // TODO: speaking timeout handling
        return;

      default:
        return;
    }

    executeSubmission();
  };

  const remainingSeconds =
    loadingSession || !session ? 1 : session.remaining_time_seconds;

  const { formattedTime, isCritical } = useExamTimer(
    remainingSeconds,
    handleTimeUp,
  );

  if (loadingSession || !session || !examConfig)
    return (
      <div className="min-h-screen bg-[#fbfbfa] p-8 font-mono text-xs text-gray-500">
        Loading active session...
      </div>
    );

  const listeningAudioUrls =
    examConfig.skill === "Listening"
      ? getListeningAudioUrls(session, sessionId)
      : null;

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
              {/* Reading and Listening each own their own submit control +
                  timing logic (ReadingExam's SubmitConfirmModal; Listening's
                  answer-transfer footer button, gated on its own 10-minute
                  countdown) with unanswered-count / window-expiry logic this
                  generic modal doesn't have. */}
              {examConfig.skill !== "Reading" &&
                examConfig.skill !== "Listening" && (
                  <button
                    onClick={() => setShowSubmitModal(true)}
                    className="bg-[#0d4d3a] hover:bg-[#09382a] text-white px-4 py-1.5 rounded-full text-xs font-semibold transition"
                  >
                    Submit Exam
                  </button>
                )}
            </div>
          </header>

          {/* Workspace Area. Reading and Listening each own their own
              independently-scrolling split panels, which the generic
              overflow-auto/p-8 wrapper used by every other skill would fight
              with (both the page and the inner panels trying to scroll), so
              they get an unpadded, height-constrained container instead. */}
          <main
            className={
              examConfig.skill === "Reading" || examConfig.skill === "Listening"
                ? "flex-1 min-h-0 overflow-hidden bg-[#fbfbfa]"
                : "flex-1 overflow-auto p-8 bg-[#fbfbfa]"
            }
          >
            {examConfig.skill === "Reading" && (
              <ReadingExam
                sessionId={sessionId}
                session={session}
                onSubmitted={handleReadingSubmitted}
                forceSubmitSignal={readingForceSubmit}
              />
            )}

            {examConfig.skill === "Listening" &&
              (listeningAudioUrls ? (
                <ListeningExam
                  sessionId={sessionId}
                  audioUrls={listeningAudioUrls}
                  rawQuestions={
                    extractRawQuestions(
                      session,
                    ) as unknown as RawReadingQuestion[]
                  }
                  onSubmitted={handleListeningSubmitted}
                />
              ) : (
                <div className="bg-white border border-gray-200/80 rounded-2xl p-8 max-w-3xl mx-auto my-8 shadow-2xs">
                  <h2 className="font-serif text-xl font-bold text-gray-900 mb-2">
                    Listening session data is incomplete
                  </h2>
                  <p className="text-sm text-gray-500 mb-5">
                    This session is missing its four section audio URLs, so the
                    listening module can&apos;t be started.
                  </p>
                  <button
                    onClick={() => router.push("/exam")}
                    className="bg-[#0d4d3a] hover:bg-[#09382a] text-white px-4 py-2 rounded-full text-xs font-semibold transition"
                  >
                    Return to Skills Workspace
                  </button>
                </div>
              ))}

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

            {examConfig.skill !== "Writing" &&
              examConfig.skill !== "Reading" &&
              examConfig.skill !== "Listening" && (
                <div className="bg-white border border-gray-200/80 rounded-2xl p-8 max-w-3xl mx-auto my-8 shadow-2xs">
                  <h2 className="font-serif text-xl font-bold text-gray-900 mb-2">
                    {examConfig.skill} exams are not available yet
                  </h2>
                  <p className="text-sm text-gray-500 mb-5">
                    This module does not have a complete exam interface, so no
                    attempt can be completed from this page.
                  </p>
                  <button
                    onClick={() => router.push("/exam")}
                    className="bg-[#0d4d3a] hover:bg-[#09382a] text-white px-4 py-2 rounded-full text-xs font-semibold transition"
                  >
                    Return to Skills Workspace
                  </button>
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
