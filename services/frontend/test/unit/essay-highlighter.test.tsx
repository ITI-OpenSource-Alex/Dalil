import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import EssayHighlighter, {
  EssayIssue,
} from "@/components/chat/essay-highlighter";
import type { CriterionEvaluation } from "@/lib/writing-api";

describe("EssayHighlighter", () => {
  it("character range highlighting correctly wraps text spans", () => {
    const text = "0123456789extra";
    const issues: EssayIssue[] = [
      {
        text: "56789",
        issue: "example issue",
        suggestion: "example suggestion",
        start: 5,
        end: 10,
        criterion: "grammar",
      },
    ];

    render(<EssayHighlighter essayText={text} issues={issues} />);

    const marks = screen.getAllByTestId("highlight-span");
    expect(marks).toHaveLength(1);
    // chars 5-9 inclusive (end is exclusive), no off-by-one in either direction
    expect(marks[0]).toHaveTextContent("56789");
    expect(marks[0].textContent).toBe(text.slice(5, 10));
  });

  it("no off-by-one for adjacent ranges", () => {
    const text = "0123456789";
    const issues: EssayIssue[] = [
      {
        text: "01234",
        issue: "issue A",
        suggestion: "suggestion A",
        start: 0,
        end: 5,
        criterion: "vocabulary",
      },
      {
        text: "56789",
        issue: "issue B",
        suggestion: "suggestion B",
        start: 5,
        end: 10,
        criterion: "cohesion",
      },
    ];

    render(<EssayHighlighter essayText={text} issues={issues} />);

    const marks = screen.getAllByTestId("highlight-span");
    expect(marks).toHaveLength(2);
    expect(marks[0]).toHaveTextContent("01234");
    expect(marks[1]).toHaveTextContent("56789");
  });

  it("overlapping ranges use first-wins strategy", () => {
    const text = "01234567";
    // Deliberately out of start order in the array to prove sorting happens
    // before overlap resolution — the earlier-starting issue (start: 0)
    // should win regardless of array position.
    const issues: EssayIssue[] = [
      {
        text: "34567",
        issue: "later issue",
        suggestion: "later suggestion",
        start: 3,
        end: 8,
        criterion: "vocabulary",
      },
      {
        text: "012345",
        issue: "earlier issue",
        suggestion: "earlier suggestion",
        start: 0,
        end: 6,
        criterion: "grammar",
      },
    ];

    render(<EssayHighlighter essayText={text} issues={issues} />);

    const marks = screen.getAllByTestId("highlight-span");
    expect(marks).toHaveLength(1);
    expect(marks[0]).toHaveTextContent("012345");
    expect(marks[0]).toHaveAttribute("data-criterion", "grammar");
  });

  it("inline_issues char ranges map correctly", () => {
    const text = "The rapid brown fox jumped over lazy dogs";

    // Mirrors WritingEvaluationPanel's flattening of CriterionEvaluation[]
    // (evaluations_full / inlineIssues) into EssayIssue[] before handing
    // off to EssayHighlighter.
    const inlineIssues: CriterionEvaluation[] = [
      {
        criterion: "grammar",
        band_score: 6,
        feedback: "Minor tense inconsistency.",
        highlighted_issues: [
          {
            text: "jumped",
            issue: "Inconsistent verb tense",
            suggestion: "Use present tense to match the rest of the essay",
            start: 20,
            end: 26,
          },
        ],
      },
      {
        criterion: "vocabulary",
        band_score: 7,
        feedback: "Good range of vocabulary.",
        highlighted_issues: [
          {
            text: "rapid",
            issue: "Slightly informal word choice",
            suggestion: "Consider 'quick' or 'swift'",
            start: 4,
            end: 9,
          },
        ],
      },
    ];

    const essayIssues: EssayIssue[] = inlineIssues.flatMap((evaluation) =>
      evaluation.highlighted_issues.map((issue) => ({
        ...issue,
        criterion: evaluation.criterion,
      })),
    );

    render(<EssayHighlighter essayText={text} issues={essayIssues} />);

    const marks = screen.getAllByTestId("highlight-span");
    expect(marks).toHaveLength(2);

    const vocabMark = marks.find(
      (m) => m.getAttribute("data-criterion") === "vocabulary",
    );
    const grammarMark = marks.find(
      (m) => m.getAttribute("data-criterion") === "grammar",
    );

    expect(vocabMark).toHaveTextContent(text.slice(4, 9));
    expect(vocabMark).toHaveTextContent("rapid");

    expect(grammarMark).toHaveTextContent(text.slice(20, 26));
    expect(grammarMark).toHaveTextContent("jumped");
  });

  it("criterion colour class applied", () => {
    const text = "He dont like apples";
    const issues: EssayIssue[] = [
      {
        text: "dont",
        issue: "Missing apostrophe",
        suggestion: "don't",
        start: 3,
        end: 7,
        criterion: "grammar",
      },
    ];

    render(<EssayHighlighter essayText={text} issues={issues} />);

    const mark = screen.getByTestId("highlight-span");
    expect(mark).toHaveAttribute("data-criterion", "grammar");
    expect(mark).toHaveClass("highlight-grammar");
  });
});
