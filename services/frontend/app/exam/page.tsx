"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ExamType, SkillArea } from "@/app/types/exam";
import { createSession, getExamProgress, type ExamProgress } from "@/lib/exam-api";
import { Sidebar } from "@/components/ui/sidebar";

export default function ExamLandingPage() {
  const router = useRouter();
  const [examType, setExamType] = useState<ExamType>("Academic");
  const [progress, setProgress] = useState<ExamProgress | null>(null);
  const [mounted, setMounted] = useState(false);
  const [startingExam, setStartingExam] = useState<SkillArea | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    getExamProgress().then(setProgress).catch(() => setProgress(null));
  }, []);

  // Check sessionStorage for an existing session to resume
  useEffect(() => {
    const saved = sessionStorage.getItem("active_exam_session");
    if (saved) {
      const { sessionId } = JSON.parse(saved);
      router.push(`/exam/shell?session=${sessionId}`);
    }
  }, [router]);

  const handleToggle = (type: ExamType) => {
    setExamType(type);
  };

  const startExam = async (skill: SkillArea) => {
    try {
      setStartingExam(skill);

      const session = await createSession(examType, skill);

      sessionStorage.setItem(
        "active_exam_session",
        JSON.stringify({
          sessionId: session.session_id,
          examType,
          skillArea: skill,
        }),
      );

      router.push(`/exam/shell?session=${session.session_id}`);
    } catch (error) {
      console.error(error);
      alert("Unable to start exam.");
    } finally {
      setStartingExam(null);
    }
  };

  const skillCards: {
    key: SkillArea;
    title: string;
    description: string;
    bgColor: string;
    icon: React.ReactNode;
  }[] = [
    {
      key: "Reading",
      title: "Reading",
      description: "Skim, scan, and answer 40 questions in 60 minutes.",
      bgColor: "bg-[#e2f4ea]",
      icon: (
        <svg
          className="w-5 h-5 text-gray-800"
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
      icon: (
        <svg
          className="w-5 h-5 text-gray-800"
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
      icon: (
        <svg
          className="w-5 h-5 text-gray-800"
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
      icon: (
        <svg
          className="w-5 h-5 text-gray-800"
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
    ? (knownBands.reduce((sum, band) => sum + band, 0) / knownBands.length).toFixed(1)
    : null;
  const weakestSkill = skillCards
    .map((card) => ({ skill: card.key, band: latestBand(card.key) }))
    .filter((item): item is { skill: SkillArea; band: number } => item.band !== null)
    .sort((a, b) => a.band - b.band)[0];

  return (
    <div className="flex min-h-screen bg-linear-to-br from-emerald-50 via-white to-orange-50 text-gray-900 font-sans">
      <Sidebar />

      <main className="flex-1 p-8 md:p-12 max-w-6xl mx-auto">
        <div
          className={`transition-all duration-700 ease-out ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          {/* Top Header Block */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
            <div>
              <p className="text-xs uppercase font-bold text-emerald-800 tracking-wider mb-2">
                IELTS PREP
              </p>
              <h1 className="text-4xl md:text-5xl font-serif font-normal text-gray-900 tracking-tight">
                Close the gap to{" "}
                <span className="italic font-serif text-amber-700">band 7</span>
              </h1>
              <p className="text-sm text-gray-500 mt-2">
                Practice IELTS modules and review your scored results.
              </p>
            </div>

            <div className="flex rounded-full border border-gray-200 bg-white p-1 text-xs font-semibold">
              {(["Academic", "General"] as ExamType[]).map((type) => (
                <button
                  key={type}
                  onClick={() => handleToggle(type)}
                  className={`rounded-full px-3 py-1.5 transition ${examType === type ? "bg-[#0d4d3a] text-white" : "text-gray-600 hover:bg-gray-100"}`}
                >
                  {type}
                </button>
              ))}
            </div>

            {/* Overall Band Card */}
            <div className="bg-white border border-gray-200/80 rounded-2xl p-4 min-w-40 shadow-2xs">
              <span className="text-xs text-gray-400 font-medium block mb-1">
                Current overall
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-serif font-semibold text-gray-900">
                  {overallBand ?? "—"}
                </span>
              </div>
            </div>
          </div>

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
                    <div className="text-right">
                      <span className="text-2xl font-serif font-bold text-gray-900 leading-none block">
                        {latestBand(card.key)?.toFixed(1) ?? "—"}
                      </span>
                      <span className="text-[10px] uppercase font-bold text-gray-500 tracking-wider">
                        CURRENT BAND
                      </span>
                    </div>
                  </div>

                  <h3 className="text-2xl font-serif font-normal text-gray-900 mb-1">
                    {card.title}
                  </h3>
                  <p className="text-xs text-gray-600 leading-relaxed max-w-xs">
                    {card.description}
                  </p>
                </div>

                {/* Card Action Controls */}
                <div className="flex justify-between items-center pt-4">
                  <div className="flex gap-1.5">
                    <button
                      disabled={
                        startingExam !== null ||
                        !["Reading", "Writing"].includes(card.key)
                      }
                      onClick={() => startExam(card.key)}
                      className="bg-white/80 hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed text-gray-700 text-l font-medium px-3 py-1 rounded-full border border-black/5 transition"
                    >
                      {startingExam === card.key
                        ? "Starting..."
                        : ["Reading", "Writing"].includes(card.key)
                          ? "Take Exam"
                          : "Coming soon"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {weakestSkill && (
            <div className="bg-white border border-gray-200/80 rounded-2xl p-4 flex items-center gap-3 text-xs text-gray-600 shadow-2xs">
              <span className="text-emerald-600 text-base">💡</span>
              <p>
                <strong className="text-gray-900 font-semibold">Practice focus:</strong>{" "}
                your latest {weakestSkill.skill} score is {weakestSkill.band.toFixed(1)},
                so it is a useful place to focus next.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
