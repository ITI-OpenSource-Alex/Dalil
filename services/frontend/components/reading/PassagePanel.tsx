"use client";

import { useRef } from "react";
import {
  usePassageHighlights,
  splitTextWithHighlights,
} from "@/app/hooks/usePassageHighlights";

interface PassagePanelProps {
  passageText: string;
  passageNumber: number;
}

/**
 * Left panel: the reading passage, independently scrollable, with
 * click-and-drag text highlighting. Highlight state is entirely local
 * (usePassageHighlights) — nothing here is ever passed to the exam's answer
 * reducer or submitted.
 */
export default function PassagePanel({
  passageText,
  passageNumber,
}: PassagePanelProps) {
  const { highlights, captureSelection, removeHighlight } =
    usePassageHighlights();

  const paragraphs = passageText.split(/\n\s*\n/).filter((p) => p.trim());

  return (
    <div
      data-testid="passage-panel"
      className="h-full overflow-y-auto border-r border-border bg-surface p-8"
    >
      <div className="mb-4">
        <span className="text-[10px] font-bold uppercase tracking-widest text-brand-fg">
          Passage {passageNumber}
        </span>
      </div>

      <article className="prose prose-sm max-w-none space-y-4 text-sm leading-relaxed whitespace-pre-wrap text-fg-muted select-text">
        {paragraphs.map((paragraph, paragraphIndex) => (
          <Paragraph
            key={paragraphIndex}
            text={paragraph}
            paragraphIndex={paragraphIndex}
            highlights={highlights.filter(
              (h) => h.paragraphIndex === paragraphIndex,
            )}
            onCaptureSelection={captureSelection}
            onRemoveHighlight={removeHighlight}
          />
        ))}
      </article>
    </div>
  );
}

function Paragraph({
  text,
  paragraphIndex,
  highlights,
  onCaptureSelection,
  onRemoveHighlight,
}: {
  text: string;
  paragraphIndex: number;
  highlights: ReturnType<typeof usePassageHighlights>["highlights"];
  onCaptureSelection: (index: number, el: HTMLElement) => void;
  onRemoveHighlight: (id: string) => void;
}) {
  const ref = useRef<HTMLParagraphElement>(null);
  const segments = splitTextWithHighlights(text, highlights);

  return (
    <p
      ref={ref}
      data-testid="passage-paragraph"
      onMouseUp={() => {
        if (ref.current) onCaptureSelection(paragraphIndex, ref.current);
      }}
    >
      {segments.map((segment, i) =>
        segment.highlightId ? (
          <mark
            key={i}
            data-testid="passage-highlight"
            title="Click to remove highlight"
            role="button"
            tabIndex={0}
            aria-label={`Remove highlight: ${segment.text}`}
            onClick={() => onRemoveHighlight(segment.highlightId!)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onRemoveHighlight(segment.highlightId!);
              }
            }}
            className="cursor-pointer rounded-xs bg-amber-200/70 hover:bg-amber-300/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
          >
            {segment.text}
          </mark>
        ) : (
          <span key={i}>{segment.text}</span>
        ),
      )}
    </p>
  );
}
