"use client";

interface Props {
  activeSection: 1 | 2 | 3;
  onSectionChange: (section: 1 | 2 | 3) => void;
}

/** Section 1/2/3 tabs. Switching sections only changes which questions (and
 * which passage) are visible — the answers map in ReadingExam's reducer is
 * keyed by absolute question number across all sections, so it's never
 * touched by a section switch and every answer survives it. */
export default function SectionTabs({ activeSection, onSectionChange }: Props) {
  return (
    <div
      role="tablist"
      aria-label="Reading sections"
      className="flex gap-1 border-b border-border px-4"
    >
      {([1, 2, 3] as const).map((section) => {
        const active = section === activeSection;
        return (
          <button
            key={section}
            type="button"
            role="tab"
            aria-selected={active}
            data-testid={`section-tab-${section}`}
            onClick={() => onSectionChange(section)}
            className={`px-4 py-2.5 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted ${
              active
                ? "border-b-2 border-brand text-brand-fg"
                : "text-fg-subtle hover:text-fg-muted"
            }`}
          >
            Section {section}
          </button>
        );
      })}
    </div>
  );
}
