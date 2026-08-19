import { useCallback, useState } from "react";

// Passage highlighting (GOA-055). Deliberately local to whatever component
// calls this hook (PassagePanel) — never lifted into the exam's shared
// reducer. The AC is explicit: "Highlight exists only in component state"
// and "Highlight is never submitted". Keeping it in its own hook, entirely
// outside the answers/session reducer, makes both of those true
// structurally: the submit code path has no reference to this state at all,
// and a highlight-only interaction re-renders just the passage tree, not
// the (much heavier) question panel.

export interface HighlightRange {
  id: string;
  paragraphIndex: number;
  start: number;
  end: number;
  text: string;
}

/**
 * Character offset of a Range boundary relative to `root`'s rendered text.
 * Works by measuring the length of a synthetic range from the start of
 * `root` to the boundary point — correct regardless of how many text nodes
 * or nested elements (e.g. already-rendered <mark> highlights) sit in
 * between, unlike a plain string .indexOf() on the paragraph text.
 */
function textOffsetWithin(
  root: Node,
  container: Node,
  offset: number,
): number {
  const measuring = document.createRange();
  measuring.selectNodeContents(root);
  measuring.setEnd(container, offset);
  return measuring.toString().length;
}

export function usePassageHighlights() {
  const [highlights, setHighlights] = useState<HighlightRange[]>([]);

  /** Call on mouseup within a paragraph element to capture the current
   * window.getSelection() as a highlight, scoped to that paragraph. */
  const captureSelection = useCallback(
    (paragraphIndex: number, paragraphEl: HTMLElement) => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
        return;
      }

      const range = selection.getRangeAt(0);
      if (!paragraphEl.contains(range.commonAncestorContainer)) {
        // Selection spans outside this paragraph (e.g. dragged across
        // paragraphs) — ignore rather than record a mismatched offset.
        return;
      }

      const text = selection.toString();
      if (!text.trim()) return;

      const start = textOffsetWithin(
        paragraphEl,
        range.startContainer,
        range.startOffset,
      );
      const end = textOffsetWithin(
        paragraphEl,
        range.endContainer,
        range.endOffset,
      );
      if (end <= start) return;

      setHighlights((prev) => [
        ...prev,
        {
          id: `${paragraphIndex}-${start}-${end}-${Date.now()}`,
          paragraphIndex,
          start,
          end,
          text,
        },
      ]);

      selection.removeAllRanges();
    },
    [],
  );

  const removeHighlight = useCallback((id: string) => {
    setHighlights((prev) => prev.filter((h) => h.id !== id));
  }, []);

  const clearHighlights = useCallback(() => setHighlights([]), []);

  return { highlights, captureSelection, removeHighlight, clearHighlights };
}

export interface TextSegment {
  text: string;
  highlightId: string | null;
}

/**
 * Splits a paragraph's plain text into segments for rendering, given the
 * highlight ranges that fall within it. Pure and independent of the DOM so
 * it's cheap to call on every render.
 */
export function splitTextWithHighlights(
  text: string,
  ranges: HighlightRange[],
): TextSegment[] {
  if (ranges.length === 0) return [{ text, highlightId: null }];

  const sorted = [...ranges].sort((a, b) => a.start - b.start);
  const segments: TextSegment[] = [];
  let cursor = 0;

  for (const range of sorted) {
    const start = Math.max(range.start, cursor);
    const end = Math.min(range.end, text.length);
    if (end <= start) continue;

    if (start > cursor) {
      segments.push({ text: text.slice(cursor, start), highlightId: null });
    }
    segments.push({ text: text.slice(start, end), highlightId: range.id });
    cursor = end;
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), highlightId: null });
  }

  return segments;
}
