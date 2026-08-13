"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { ExamType, SkillArea } from "@/app/types/exam";
import {
  createSession,
  getExamProgress,
  type ExamProgress,
} from "@/lib/exam-api";
import { startListeningSession } from "@/lib/listening-api";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";
import { Alert, Button, Card, PageContainer } from "@/components/ui";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";

export default function ExamLandingPage() {
  const router = useRouter();
  const {
    user,
    status: profileStatus,
    error: profileError,
    retry: retryProfile,
  } = useCurrentUser();
  const upgrade = useUpgradePrompt();
  const [examType, setExamType] = useState<ExamType>("Academic");
  const [progress, setProgress] = useState<ExamProgress | null>(null);
  const [mounted, setMounted] = useState(false);
  const [startingExam, setStartingExam] = useState<SkillArea | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  // doc 11: tracked so the error banner's Retry action re-attempts the
  // same skill the user actually clicked, not a hardcoded one.
  const [lastAttemptedSkill, setLastAttemptedSkill] =
    useState<SkillArea | null>(null);
  const [resumableSessionId, setResumableSessionId] = useState<string | null>(
    null,
  );

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    getExamProgress()
      .then(setProgress)
      .catch(() => setProgress(null));
  }, []);

  // doc 10: this previously redirected into the shell automatically and
  // unguarded -- a corrupted stored value threw during the effect (no
  // try/catch around JSON.parse), and even a well-formed-but-stale session
  // id caused a surprising, silent redirect the user never asked for. Now:
  // malformed JSON is treated the same as "nothing to resume" (cleared,
  // no redirect); a well-formed value surfaces an explicit resume/discard
  // choice below instead of navigating automatically. The other half of
  // this fix -- what happens when the shell then fails to load a stale
  // session id -- lives in exam/shell/page.tsx's loadSession catch block.
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem("active_exam_session");
      if (!saved) return;

      const parsed = JSON.parse(saved);
      if (parsed && typeof parsed.sessionId === "string") {
        setResumableSessionId(parsed.sessionId);
      } else {
        sessionStorage.removeItem("active_exam_session");
      }
    } catch {
      sessionStorage.removeItem("active_exam_session");
    }
  }, []);

  const handleResumeSession = () => {
    if (!resumableSessionId) return;
    router.push(`/exam/shell?session=${resumableSessionId}`);
  };

  const handleDiscardSession = () => {
    sessionStorage.removeItem("active_exam_session");
    setResumableSessionId(null);
  };

  const handleToggle = (type: ExamType) => {
    setExamType(type);
  };

  const startExam = async (skill: SkillArea) => {
    // GOA-035/BUG-047: an exam session created under the wrong user id
    // passes creation but then 403s at submit time via the Gateway's
    // examOwnership check -- failing fast here, before a candidate has
    // answered a full exam, is far cheaper than that failure mode.
    if (profileStatus === "loading" || profileStatus === "idle" || !user) {
      setStartError(
        "Your profile is still loading — please wait a moment and try again.",
      );
      setLastAttemptedSkill(skill);
      return;
    }

    setStartError(null);

    // Short-circuit on a known Free account rather than spending a request to
    // be told what the profile already says. The catch below still handles the
    // case where the tier changed under us -- the server stays authoritative,
    // this only saves a round trip and shows the dialog instantly.
    if (user.subscriptionTier !== "paid") {
      upgrade.show("exam");
      return;
    }

    try {
      setStartingExam(skill);

      // The user id is no longer passed from the browser: the Gateway derives
      // it from the JWT, so it cannot be spoofed by the caller. The profile
      // guard above still runs, because starting an exam before identity has
      // resolved is what BUG-047 was about.
      //
      // Listening does not go through createSession: its start endpoint also
      // returns the four section audio URLs, which the generic session object
      // does not carry. The shell reads them back out of the stored start
      // payload (see getListeningAudioUrls in exam/shell/page.tsx), so both
      // the session marker and the raw start response have to be persisted
      // here.
      if (skill === "Listening") {
        const listeningSession = await startListeningSession(examType);

        sessionStorage.setItem(
          "active_exam_session",
          JSON.stringify({
            sessionId: listeningSession.session_id,
            examType,
            skillArea: skill,
          }),
        );

        sessionStorage.setItem(
          `listening_start_${listeningSession.session_id}`,
          JSON.stringify(listeningSession),
        );

        router.push(`/exam/shell?session=${listeningSession.session_id}`);
        return;
      }

      const session = await createSession(examType, skill);

      sessionStorage.setItem(
        "active_exam_session",
        JSON.stringify({
          sessionId: session.session_id,
          examType,
          skillArea: skill,
        }),
      );

      if (skill === "Speaking") {
        router.push(
          `/practice/speaking?mode=exam&session=${session.session_id}`,
        );
      } else {
        router.push(`/exam/shell?session=${session.session_id}`);
      }
    } catch (error) {
      // A paid-tier refusal is a product decision, not a fault. The whole
      // /api/exam group is gated (GOA-059), so on a Free account this is the
      // *expected* outcome of pressing "Take Exam" -- and it used to print
      // the Gateway's raw 403 JSON into the amber banner below. It now opens
      // the same upgrade dialog every other paid feature uses, with no error
      // banner at all.
      if (upgrade.handle(error, "exam")) {
        setLastAttemptedSkill(null);
        return;
      }
      console.error(error);
      // doc 11: a native alert() here was one of the most jarring failure
      // modes available on a shared screen -- replaced with the same
      // inline, dismissible banner already used for the profile-loading
      // guard above, so the two related failure states share one visual
      // treatment instead of two.
      setStartError(`Unable to start the ${skill} exam. Please try again.`);
      setLastAttemptedSkill(skill);
    } finally {
      setStartingExam(null);
    }
  };

  const handleRetryStartExam = () => {
    if (lastAttemptedSkill) {
      void startExam(lastAttemptedSkill);
    }
  };

  const skillCards: {
    key: SkillArea;
    title: string;
    description: string;
    bgColor: string;
    icon: React.ReactNode;
    available: boolean;
  }[] = [
    {
      key: "Reading",
      title: "Reading",
      description: "Skim, scan, and answer 40 questions in 60 minutes.",
      bgColor: "bg-[#e2f4ea]",
      available: true,
      icon: (
        <svg
          className="w-5 h-5 text-fg"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth="1.75"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
          />
        </svg>
      ),
    },
    {
      key: "Listening",
      title: "Listening",
      description: "Four sections, increasing difficulty, 30 minutes.",
      bgColor: "bg-[#faedd4]",
      available: true,
      icon: (
        <svg
          className="w-5 h-5 text-fg"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth="1.75"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 100-6 3 3 0 000 6z"
          />
        </svg>
      ),
    },
    {
      key: "Writing",
      title: "Writing",
      description: "Task 1 (report) + Task 2 (essay) in 60 minutes.",
      bgColor: "bg-[#f2e7f7]",
      available: true,
      icon: (
        <svg
          className="w-5 h-5 text-fg"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth="1.75"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
          />
        </svg>
      ),
    },
    {
      key: "Speaking",
      title: "Speaking",
      description: "11-14 minute face-to-face interview with examiner.",
      bgColor: "bg-[#e3edf7]",
      available: true,
      icon: (
        <svg
          className="w-5 h-5 text-fg"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth="1.75"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 100-6 3 3 0 000 6z"
          />
        </svg>
      ),
    },
  ];

  const latestBand = (skill: SkillArea) => {
    const scores = progress?.[skill.toLowerCase() as keyof ExamProgress] ?? [];
    return scores[scores.length - 1]?.band ?? null;
  };
  const knownBands = skillCards
    .map((card) => latestBand(card.key))
    .filter((band): band is number => band !== null);
  const overallBand = knownBands.length
    ? (
        knownBands.reduce((sum, band) => sum + band, 0) / knownBands.length
      ).toFixed(1)
    : null;
  const weakestSkill = skillCards
    .map((card) => ({ skill: card.key, band: latestBand(card.key) }))
    .filter(
      (item): item is { skill: SkillArea; band: number } => item.band !== null,
    )
    .sort((a, b) => a.band - b.band)[0];

  // Only once identity has actually resolved: assuming Free while the profile
  // is still loading would flash a paywall badge at a paying subscriber.
  const isFreeTier =
    profileStatus === "success" && user?.subscriptionTier !== "paid";
  const identityLoading =
    profileStatus === "loading" || profileStatus === "idle";

  return (
    <PageContainer
      size="2xl"
      className="min-h-screen bg-linear-to-br from-brand-subtle via-surface to-warning-subtle text-fg"
    >
      <div
        className={`transition-all duration-700 ease-out ${
          mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
        }`}
      >
        {/* Top Header Block */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
          <div>
            <p className="text-xs uppercase font-bold text-brand-fg tracking-wider mb-2">
              IELTS PREP
            </p>
            <h1 className="text-4xl md:text-5xl font-serif font-normal text-fg tracking-tight">
              Close the gap to{" "}
              <span className="italic font-serif text-warning-fg">band 7</span>
            </h1>
            <p className="text-sm text-fg-subtle mt-2">
              Practice IELTS modules and review your scored results.
            </p>
          </div>

          <div className="flex rounded-full border border-border bg-surface p-1 text-xs font-semibold">
            {(["Academic", "General"] as ExamType[]).map((type) => (
              <button
                key={type}
                onClick={() => handleToggle(type)}
                aria-pressed={examType === type}
                className={`rounded-full px-3 py-1.5 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted ${examType === type ? "bg-brand text-fg-on-brand" : "text-fg-muted hover:bg-canvas-subtle"}`}
              >
                {type}
              </button>
            ))}
          </div>

          {/* Overall Band Card */}
          <Card padding="sm" className="min-w-40">
            <span className="text-xs text-fg-subtle font-medium block mb-1">
              Current overall
            </span>
            <div className="flex items-center gap-2">
              <span className="text-3xl font-serif font-semibold text-fg">
                {overallBand ?? "—"}
              </span>
              {overallBand !== null && (
                <ExplainWithDalilButton
                  context={{
                    kind: "exam_score",
                    title: `your current IELTS practice average ${overallBand}`,
                    facts: compactFacts([
                      fact("Displayed average", overallBand),
                      ...skillCards.map((card) =>
                        fact(
                          `${card.title} latest band`,
                          latestBand(card.key)?.toFixed(1),
                        ),
                      ),
                    ]),
                    limitations: [
                      "The dashboard average uses only the latest available practice band for each completed skill.",
                      "This is not an official IELTS result.",
                    ],
                  }}
                  prompt={`How is my current IELTS practice average ${overallBand} formed from my latest skill scores? Tell me which skill is pulling it down most.`}
                />
              )}
            </div>
          </Card>
        </div>

        {resumableSessionId && (
          <Card
            padding="sm"
            className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <p className="text-sm text-fg-muted">
              You have an exam in progress. Would you like to resume it?
            </p>
            <div className="flex shrink-0 gap-2">
              <Button size="sm" onClick={handleResumeSession}>
                Resume in-progress exam
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={handleDiscardSession}
              >
                Discard
              </Button>
            </div>
          </Card>
        )}

        {profileStatus === "error" && (
          <Alert
            tone="danger"
            className="mb-6"
            actions={
              <Button variant="danger" size="sm" onClick={retryProfile}>
                Retry
              </Button>
            }
          >
            {profileError ?? "Failed to load your profile."}
          </Alert>
        )}

        {startError && (
          <Alert
            tone="warning"
            className="mb-6"
            actions={
              <>
                <Button
                  size="sm"
                  onClick={handleRetryStartExam}
                  disabled={startingExam !== null || identityLoading}
                >
                  Retry
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setStartError(null)}
                >
                  Dismiss
                </Button>
              </>
            }
          >
            {startError}
          </Alert>
        )}

        {/* Grid of Custom Styled Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {skillCards.map((card, i) => (
            <div
              key={card.key}
              style={{ transitionDelay: mounted ? `${i * 90}ms` : "0ms" }}
              className={`${card.bgColor} rounded-3xl p-7 flex flex-col justify-between h-56 transition-all duration-700 ease-out hover:shadow-md ${
                mounted
                  ? "opacity-100 translate-y-0"
                  : "opacity-0 translate-y-6"
              }`}
            >
              <div>
                <div className="flex justify-between items-start mb-2">
                  <div className="p-1">{card.icon}</div>
                  <div className="flex items-start gap-1">
                    <div className="text-right">
                      <span className="text-2xl font-serif font-bold text-fg leading-none block">
                        {latestBand(card.key)?.toFixed(1) ?? "—"}
                      </span>
                      <span className="text-[10px] uppercase font-bold text-fg-subtle tracking-wider">
                        CURRENT BAND
                      </span>
                    </div>
                    {latestBand(card.key) !== null && (
                      <ExplainWithDalilButton
                        context={{
                          kind: "exam_score",
                          title: `your latest ${card.title} practice band ${latestBand(card.key)?.toFixed(1)}`,
                          facts: compactFacts([
                            fact("Skill", card.title),
                            fact(
                              "Latest practice band",
                              latestBand(card.key)?.toFixed(1),
                            ),
                            fact(
                              "Recorded attempts",
                              progress?.[
                                card.key.toLowerCase() as keyof ExamProgress
                              ]?.length,
                            ),
                          ]),
                          limitations: [
                            "This summary does not include the question- or criterion-level evidence; open the result for the full breakdown.",
                          ],
                        }}
                        prompt={`What does my latest ${card.title} practice band ${latestBand(card.key)?.toFixed(1)} mean, and what should I inspect in the full result before deciding what to practise next?`}
                        className="-mt-1"
                      />
                    )}
                  </div>
                </div>

                <h2 className="text-2xl font-serif font-normal text-fg mb-1">
                  {card.title}
                </h2>
                <p className="text-xs text-fg-muted leading-relaxed max-w-xs">
                  {card.description}
                </p>
              </div>

              {/* Card Action Controls */}
              <div className="flex justify-between items-center pt-4">
                <div className="flex items-center gap-1.5">
                  {card.available ? (
                    <>
                      <button
                        disabled={startingExam !== null}
                        onClick={() => startExam(card.key)}
                        className="bg-white/80 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed text-fg-muted text-l font-medium px-3 py-1 rounded-full border border-black/5 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
                      >
                        {startingExam === card.key
                          ? "Starting..."
                          : "Take Exam"}
                      </button>
                      {/* The gate is stated up front rather than discovered
                            by pressing the button. Clicking still works — it
                            opens the upgrade dialog — so this is information,
                            not a second disabled state. */}
                      {isFreeTier && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-white/60 px-2 py-0.5 text-[11px] font-semibold text-fg-muted">
                          <Sparkles size={11} aria-hidden="true" />
                          Pro
                        </span>
                      )}
                    </>
                  ) : (
                    <span
                      title={`${card.title} simulation is not available yet.`}
                      className="inline-flex items-center gap-1 bg-white/50 text-fg-subtle text-l font-medium px-3 py-1 rounded-full border border-black/5 cursor-not-allowed select-none"
                    >
                      Coming soon
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {weakestSkill && (
          <Card
            padding="sm"
            className="flex items-center gap-3 text-xs text-fg-muted"
          >
            <span className="text-brand-fg text-base" aria-hidden="true">
              💡
            </span>
            <p>
              <strong className="text-fg font-semibold">Practice focus:</strong>{" "}
              your latest {weakestSkill.skill} score is{" "}
              {weakestSkill.band.toFixed(1)}, so it is a useful place to focus
              next.
            </p>
          </Card>
        )}
      </div>
    </PageContainer>
  );
}
