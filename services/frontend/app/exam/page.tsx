"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ExamType, SkillArea } from "@/app/types/exam";

export default function ExamLandingPage() {
  const router = useRouter();
  const [examType, setExamType] = useState<ExamType>("Academic");
  const [profileScores, setProfileScores] = useState({
    Reading: "7.5",
    Listening: "8.0",
    Speaking: "6.5",
    Writing: "7.0",
  });
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
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
    // Update user profile via mock API patch
    fetch("/api/profile", {
      method: "PATCH",
      body: JSON.stringify({ preferredExamType: type }),
    });
  };

  const startExam = async (skill: SkillArea) => {
    // Scaffold architecture call to GOA-048 Exam Service
    const res = await fetch("/api/exams/start", {
      method: "POST",
      body: JSON.stringify({ examType, skill }),
    });
    const data = await res.json();

    sessionStorage.setItem(
      "active_exam_session",
      JSON.stringify({ sessionId: data.sessionId, examType, skillArea: skill }),
    );
    router.push(`/exam/shell?session=${data.sessionId}`);
  };

  return (
    <div className="min-h-screen bg-linear-to-br from-emerald-50 via-white to-yellow-50 text-black p-6 md:p-12">
      <div
        className={`max-w-5xl mx-auto transition-all duration-700 ease-out ${
          mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
        }`}
      >
        <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-gray-200 pb-6 mb-8">
          <div className="space-y-1">
            <h1 className="text-3xl font-black text-black tracking-tight uppercase">
              IELTS Preparation Portal
            </h1>
            <p className="text-sm text-gray-500">
              Select a skill below to begin practicing and improve your target
              band score.
            </p>
          </div>

          {/* Toggle Switch */}
          <div className="flex bg-yellow-50 border border-gray-300 rounded-lg p-1 font-semibold text-sm">
            <button
              onClick={() => handleToggle("Academic")}
              className={`px-4 py-1.5 rounded-md transition ${
                examType === "Academic"
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "text-gray-600 hover:text-black"
              }`}
            >
              Academic
            </button>
            <button
              onClick={() => handleToggle("General")}
              className={`px-4 py-1.5 rounded-md transition ${
                examType === "General"
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "text-gray-600 hover:text-black"
              }`}
            >
              General Training
            </button>
          </div>
        </header>

        {/* Grid of Skills */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {(["Reading", "Listening", "Speaking", "Writing"] as SkillArea[]).map(
            (skill, i) => (
              <div
                key={skill}
                style={{ transitionDelay: mounted ? `${i * 90}ms` : "0ms" }}
                className={`bg-white border border-gray-200 rounded-xl p-6 flex flex-col justify-between shadow-sm hover:border-emerald-500/50 transition-all duration-700 ease-out ${
                  mounted
                    ? "opacity-100 translate-y-0"
                    : "opacity-0 translate-y-6"
                }`}
              >
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-xl font-bold tracking-tight text-black uppercase">
                      {skill}
                    </h3>
                    <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs px-2.5 py-1 rounded-md font-bold uppercase">
                      {examType}
                    </span>
                  </div>
                  <p className="text-gray-500 text-sm mb-6">
                    Last Evaluated Band:{" "}
                    <span className="font-bold text-black text-lg font-mono">
                      {profileScores[skill] || "N/A"}
                    </span>
                  </p>
                </div>
                <button
                  onClick={() => startExam(skill)}
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 rounded-lg shadow-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500"
                >
                  START EXAM
                </button>
              </div>
            ),
          )}
        </div>
      </div>
    </div>
  );
}
