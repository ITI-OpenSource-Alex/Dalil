"use client";

import { ArrowLeft } from "lucide-react";
import type { SkillArea } from "@/app/types/exam";

// GOA-035/BUG-047 doc 08: replaces the exam shell's dashed-grey
// "Interactive Simulation Workspace" placeholder for skills that aren't
// built yet. Layer 1 (the "Coming soon" badge on /exam's skill cards)
// keeps this from being reached in ordinary use -- this is Layer 2, for
// the case the shell is still reached directly (a stale sessionStorage
// entry, or a manually-typed URL).
const PLANNED_CAPABILITIES: Record<"Listening" | "Speaking", string[]> = {
  Listening: [
    "Seek-disabled audio player",
    "Sequential section progression",
    "A scratch pad for notes",
    "A 10-minute answer-transfer period",
  ],
  Speaking: [
    "The strict 3-part IELTS structure",
    "A 60-second preparation timer",
    "A live waveform visualizer",
    "Holistic 4-agent evaluation",
  ],
};

interface ComingSoonPanelProps {
  skill: SkillArea;
  onBack: () => void;
}

export default function ComingSoonPanel({ skill, onBack }: ComingSoonPanelProps) {
  const capabilities =
    skill === "Listening" || skill === "Speaking"
      ? PLANNED_CAPABILITIES[skill]
      : [];

  return (
    <div className="bg-white border border-gray-200/80 rounded-2xl p-8 max-w-3xl mx-auto my-8 shadow-2xs text-center">
      <span className="inline-flex items-center rounded-full bg-[#e2f4ea] text-[#0d4d3a] px-3 py-1 text-xs font-semibold">
        Coming soon
      </span>

      <h2 className="mt-4 text-2xl font-serif font-normal text-gray-900">
        {skill} simulation isn&apos;t built yet
      </h2>

      <p className="mt-2 text-sm text-gray-500 max-w-md mx-auto">
        Reading is complete; {skill} is next. Here&apos;s what&apos;s already
        scoped for it:
      </p>

      {capabilities.length > 0 && (
        <ul className="mt-6 space-y-2 text-left max-w-sm mx-auto">
          {capabilities.map((capability) => (
            <li
              key={capability}
              className="flex items-start gap-2 text-sm text-gray-700"
            >
              <span
                className="mt-1.5 h-1.5 w-1.5 rounded-full bg-[#0d4d3a] shrink-0"
                aria-hidden="true"
              />
              {capability}
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={onBack}
        className="mt-8 inline-flex items-center gap-2 bg-[#0d4d3a] hover:bg-[#09382a] text-white px-4 py-2 rounded-full text-xs font-semibold transition"
      >
        <ArrowLeft size={14} />
        Back to Skills Workspace
      </button>
    </div>
  );
}
