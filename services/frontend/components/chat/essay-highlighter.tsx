"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import type { HighlightedIssue } from "@/lib/writing-api";

export type EssayIssue = HighlightedIssue & { criterion: string };

interface EssayHighlighterProps {
  essayText: string;
  issues: EssayIssue[];
}

type PlainSegment = {
  type: "text";
  content: string;
};

type MarkSegment = {
  type: "mark";
  content: string;
  issue: EssayIssue;
  index: number;
};

type Segment = PlainSegment | MarkSegment;

/**
 * The one criterion → colour mapping in the app: grammar red, cohesion orange,
 * vocabulary blue, task response purple.
 *
 * Exported (GOA-058) so the Writing exam UI can colour its band bars and
 * criterion chips from the same source the inline highlights use. A second
 * copy of these values would drift, and the whole point of the colour coding is
 * that a student learns one vocabulary and it means the same thing everywhere.
 * Export only — the values and the chat behaviour are unchanged.
 */
export const CRITERION_COLOURS: Record<
  string,
  { bg: string; border: string; text: string; className: string }
> = {
  grammar: {
    bg: "rgba(255, 77, 77, 0.16)",
    border: "rgba(255, 77, 77, 0.45)",
    text: "#B42318",
    className: "highlight-grammar",
  },
  cohesion: {
    bg: "rgba(255, 140, 0, 0.16)",
    border: "rgba(255, 140, 0, 0.45)",
    text: "#9A3412",
    className: "highlight-cohesion",
  },
  vocabulary: {
    bg: "rgba(59, 130, 246, 0.16)",
    border: "rgba(59, 130, 246, 0.45)",
    text: "#1E40AF",
    className: "highlight-vocabulary",
  },
  task_response: {
    bg: "rgba(139, 92, 246, 0.16)",
    border: "rgba(139, 92, 246, 0.45)",
    text: "#6D28D9",
    className: "highlight-task_response",
  },
};

export const DEFAULT_CRITERION_COLOUR = {
  bg: "rgba(107, 114, 128, 0.16)",
  border: "rgba(107, 114, 128, 0.45)",
  text: "#374151",
  className: "highlight-default",
};

const criterionLabels: Record<string, string> = {
  grammar: "Grammar",
  cohesion: "Cohesion & Coherence",
  vocabulary: "Vocabulary",
  task_response: "Task Response",
};

/**
 * Sorts issues by start offset and resolves overlaps by taking the first
 * (earliest-starting) match — any subsequent issue whose start falls before
 * the previous issue's end is dropped. Invalid ranges (start >= end, or end
 * past the text length) are also dropped.
 */
function resolveNonOverlappingIssues(
  text: string,
  issues: EssayIssue[],
): EssayIssue[] {
  const sorted = [...issues].sort((a, b) => a.start - b.start);
  const resolved: EssayIssue[] = [];
  let cursor = 0;

  for (const issue of sorted) {
    if (
      issue.start < 0 ||
      issue.end > text.length ||
      issue.start >= issue.end
    ) {
      continue;
    }
    if (issue.start < cursor) {
      // Overlaps with an already-placed issue — first match wins.
      continue;
    }
    resolved.push(issue);
    cursor = issue.end;
  }

  return resolved;
}

function buildSegments(text: string, issues: EssayIssue[]): Segment[] {
  const resolved = resolveNonOverlappingIssues(text, issues);
  const segments: Segment[] = [];
  let pos = 0;

  resolved.forEach((issue, index) => {
    if (issue.start > pos) {
      segments.push({ type: "text", content: text.slice(pos, issue.start) });
    }
    segments.push({
      type: "mark",
      content: text.slice(issue.start, issue.end),
      issue,
      index,
    });
    pos = issue.end;
  });

  if (pos < text.length) {
    segments.push({ type: "text", content: text.slice(pos) });
  }

  return segments;
}

function HighlightMark({ segment }: { segment: MarkSegment }) {
  const colours =
    CRITERION_COLOURS[segment.issue.criterion] ?? DEFAULT_CRITERION_COLOUR;

  return (
    <Tooltip.Root delayDuration={150}>
      <Tooltip.Trigger asChild>
        <mark
          data-testid="highlight-span"
          data-criterion={segment.issue.criterion}
          data-issue-index={segment.index}
          className={colours.className}
          style={{
            background: colours.bg,
            border: `1px solid ${colours.border}`,
            borderRadius: "3px",
            padding: "0 1px",
            cursor: "help",
          }}
        >
          {segment.content}
        </mark>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          data-testid="highlight-tooltip"
          side="top"
          align="start"
          sideOffset={6}
          className="z-50 w-64 rounded-md border border-[#E4EAE4] bg-white shadow-md p-2.5 space-y-1"
        >
          <span
            className="text-[10px] font-semibold uppercase tracking-wide"
            style={{ color: colours.text }}
          >
            {criterionLabels[segment.issue.criterion] ??
              segment.issue.criterion}
          </span>
          <p className="text-xs text-[#1D291E] leading-relaxed">
            {segment.issue.issue}
          </p>
          <p className="text-xs text-[#667267] leading-relaxed">
            <span className="font-medium text-[#3A463B]">Suggestion: </span>
            {segment.issue.suggestion}
          </p>
          <Tooltip.Arrow className="fill-white" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export default function EssayHighlighter({
  essayText,
  issues,
}: EssayHighlighterProps) {
  const segments = buildSegments(essayText, issues);

  return (
    <Tooltip.Provider delayDuration={150}>
      <div className="text-sm text-[#1D291E] leading-relaxed whitespace-pre-wrap">
        {segments.map((segment, segmentIdx) =>
          segment.type === "text" ? (
            <span key={`text-${segmentIdx}`}>{segment.content}</span>
          ) : (
            <HighlightMark key={`mark-${segment.index}`} segment={segment} />
          ),
        )}
      </div>
    </Tooltip.Provider>
  );
}
