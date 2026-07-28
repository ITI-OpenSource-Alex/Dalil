"use client";

import type { ReadingSectionBreakdown } from "@/app/types/reading";

interface Props {
  sectionBreakdown: Record<string, ReadingSectionBreakdown>;
}

const SECTION_KEYS = ["section_1", "section_2", "section_3"] as const;
const SECTION_LABELS: Record<(typeof SECTION_KEYS)[number], string> = {
  section_1: "Section 1",
  section_2: "Section 2",
  section_3: "Section 3",
};

/** Section 1/2/3 scores as progress bars. Unlike the exam-taking view's
 * section tabs (which must derive section from question number client-side
 * — see lib/reading-sections.ts), this reads section_breakdown directly
 * from the submit response: the backend already buckets it there, so no
 * client derivation is needed or should be attempted here. */
export default function SectionBreakdownBars({ sectionBreakdown }: Props) {
  return (
    <div
      data-testid="section-breakdown-bars"
      className="rounded-2xl border border-gray-200/80 bg-white p-6 shadow-2xs"
    >
      <h3 className="mb-4 text-sm font-bold text-gray-900">
        Section Breakdown
      </h3>

      <div className="space-y-3">
        {SECTION_KEYS.map((key) => {
          const stat = sectionBreakdown[key];
          if (!stat) return null;

          const percentage = stat.total === 0 ? 0 : (stat.correct / stat.total) * 100;

          return (
            <div key={key} data-testid={`section-bar-${key}`}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-medium text-gray-700">
                  {SECTION_LABELS[key]}
                </span>
                <span className="font-semibold text-gray-900">
                  {stat.correct}/{stat.total}
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                <div
                  className="h-full rounded-full bg-emerald-600 transition-all"
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
