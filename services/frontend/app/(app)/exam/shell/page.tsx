"use client";

import { Suspense, useCallback, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useExamTimer } from "@/app/hooks/useExamTimer";
import { ExamType, SkillArea, ExamStatus } from "@/app/types/exam";
import { getSession, sendHeartbeat, submitSession } from "@/lib/exam-api";

// Well inside the backend's 10-minute grace window, so several consecutive
// failures are survivable.
const HEARTBEAT_INTERVAL_MS = 60_000;
// import { evaluateEssay } from "@/lib/writing-api";
import type { ExamSessionResponse } from "@/lib/exam-api";
import ReadingExam from "@/components/reading/ReadingExam";
import WritingExam from "@/components/writing/WritingExam";
import ComingSoonPanel from "@/components/exam/ComingSoonPanel";
import { storeReadingResult } from "@/lib/reading-result-storage";
import type {
  NormalizedReadingQuestion,
  ReadingSubmitResponse,
} from "@/app/types/reading";
import { Alert, Button } from "@/components/ui";

// useSearchParams() opts the page into client-side rendering during
// prerendering, which Next.js requires to be wrapped in a Suspense boundary
// (https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout) —
// otherwise `next build`'s static export of this route fails.
export default function ExamShell() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-canvas p-8 font-mono text-xs text-fg-subtle">
          Loading active session...
        </div>
      }
    >
      <ExamShellContent />
    </Suspense>
  );
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
  // doc 11: a failed submit used to only console.error, leaving `status` stuck
  // on "evaluating" -- the full-screen "Analyzing performance..." overlay stayed
  // up forever with no way out short of a reload. The status reset below clears
  // the overlay; this surfaces the reason so the retry is an informed one.
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [mounted, setMounted] = useState(false);
  // Bumped to trigger ReadingExam's own submit on timer expiry — see
  // ReadingExam's forceSubmitSignal prop for why this can't just reuse
  // a generic submission path here.
  const [readingForceSubmit, setReadingForceSubmit] = useState(0);
  // The same mechanism for Writing. Writing owns its own per-task submits
  // (GOA-058), so on expiry it is told to flush whatever is unsubmitted rather
  // than having the shell post on its behalf.
  const [writingForceSubmit, setWritingForceSubmit] = useState(0);

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

  /**
   * Generic whole-exam submit, used by the skills that have no submit flow of
   * their own. Reading and Writing both opt out: Reading owns its own confirm
   * modal, and Writing submits one task at a time (GOA-058).
   */
  const executeSubmission = async () => {
    setShowSubmitModal(false);

    try {
      setStatus("evaluating");

      setSubmissionError(null);
      await submitSession(sessionId, {});

      router.push(`/exam/results?session=${sessionId}&skill=${examConfig?.skill}`);
    } catch (err) {
      console.error(err);
      // Reset so the "Analyzing performance..." overlay clears and the exam
      // (and a retry) are usable again. Applies identically to the manual
      // Submit button and the timer's auto-submit on expiry -- both land here.
      setStatus("in_progress");
      setSubmissionError(
        err instanceof Error
          ? err.message
          : "Failed to submit your exam. Please try again.",
      );
    }
  };

  /**
   * Both Writing tasks are in, so the exam service has scored the session and
   * the combined weighted result exists. No overlay is shown on the way out —
   * the evaluations already ran per task, so there is nothing left to wait for.
   */
  const handleWritingCompleted = useCallback(() => {
    router.push(`/exam/results?session=${sessionId}&skill=Writing`);
  }, [router, sessionId]);

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

  const handleTimeUp = () => {
    // useExamTimer is called below with session?.remaining_time_seconds ?? 0
    // — before the session finishes loading, that's 0, which makes the
    // timer fire an immediate (spurious) time-up on mount, before
    // examConfig exists. Ignoring that null-session case here is required
    // for Reading (and doesn't change Writing's real-timeout behavior,
    // which only ever fires once examConfig is already set).
    if (!examConfig) return;
    if (examConfig.skill === "Reading") {
      setReadingForceSubmit((n) => n + 1);
      return;
    }
    // Writing flushes its own unsubmitted tasks: only it knows which of the two
    // have already been evaluated, and each submit needs that task's own text
    // and number.
    if (examConfig.skill === "Writing") {
      setWritingForceSubmit((n) => n + 1);
      return;
    }
    executeSubmission();
  };

  const { formattedTime, isCritical, secondsLeft } = useExamTimer(
    session?.remaining_time_seconds ?? 0,
    handleTimeUp,
  );

  if (loadingSession || !session || !examConfig)
    return (
      <div className="min-h-screen bg-[#fbfbfa] p-8 font-mono text-xs text-gray-500">
        Loading active session...
      </div>
    );

  return (
    <>
      <div className="flex h-screen min-w-3xl flex-col overflow-hidden bg-canvas text-fg select-none">
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
          <header className="h-16 border-b border-border px-8 flex justify-between items-center bg-surface shrink-0">
            <div className="flex items-center gap-3">
              <span className="font-serif text-lg font-bold text-fg">
                {examConfig.skill} Module
              </span>
              <span className="bg-brand-subtle text-brand-fg px-2.5 py-0.5 text-xs font-semibold rounded-full">
                {examConfig.type}
              </span>
            </div>

            <div className="flex items-center gap-4">
              <div
                className={`font-mono text-sm font-semibold px-3 py-1 rounded-full border transition-colors ${
                  isCritical
                    ? "bg-danger-subtle text-danger border-danger-border animate-pulse"
                    : "bg-canvas-subtle text-fg-muted border-border"
                }`}
              >
                {formattedTime}
              </div>
              {/* Reading has its own submit control + confirmation modal
                  (ReadingExam / SubmitConfirmModal) with unanswered-count
                  logic this generic modal doesn't have — see
                  components/reading/SubmitConfirmModal.tsx for why that's a
                  separate component rather than a reuse of this one.

                  Writing opts out for a different reason: there is no single
                  "submit the exam" action to offer. Each task is submitted and
                  evaluated on its own, and the session completes when the
                  second one lands. A generic submit here could only post an
                  empty payload over the top of that. */}
              {examConfig.skill !== "Reading" &&
                examConfig.skill !== "Writing" && (
                  <Button size="sm" onClick={() => setShowSubmitModal(true)}>
                    Submit Exam
                  </Button>
                )}
            </div>
          </header>

          {/* Workspace Area. Reading owns its own independently-scrolling
              split panels, which the generic overflow-auto/p-8 wrapper used
              by every other skill would fight with (both the page and the
              inner panels trying to scroll), so it gets an unpadded,
              height-constrained container instead. */}
          <main
            className={
              examConfig.skill === "Reading"
                ? "flex-1 min-h-0 overflow-hidden bg-canvas"
                : "flex-1 overflow-auto p-8 bg-canvas"
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

            {examConfig.skill === "Writing" && (
              <WritingExam
                sessionId={sessionId}
                session={session}
                examType={examConfig.type}
                secondsLeft={secondsLeft}
                forceSubmitSignal={writingForceSubmit}
                onCompleted={handleWritingCompleted}
              />
            )}

            {examConfig.skill !== "Writing" && examConfig.skill !== "Reading" && (
              <ComingSoonPanel
                skill={examConfig.skill}
                onBack={() => router.push("/exam")}
              />
            )}

            {submissionError && (
              <Alert tone="danger" className="mt-6 max-w-3xl mx-auto">
                {submissionError}
              </Alert>
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
          <div className="bg-surface border border-border p-6 max-w-sm w-full rounded-2xl shadow-xl">
            <h3 className="text-base font-bold text-fg mb-1">
              Submit Examination?
            </h3>
            <p className="text-xs text-fg-subtle mb-6">
              Your responses will be evaluated using AI scoring guidelines.
            </p>
            <div className="flex justify-end gap-2 text-xs font-semibold">
              <Button variant="secondary" size="sm" onClick={() => setShowSubmitModal(false)}>
                Cancel
              </Button>
              <Button size="sm" onClick={executeSubmission}>
                Submit & Exit
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
