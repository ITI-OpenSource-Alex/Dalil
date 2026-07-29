import { describe, expect, it } from "vitest";
import {
  countWords,
  elapsedMinutes,
  formatWeightedFormula,
  isUnderMinimum,
  toEssayIssues,
  topIssuePerCriterion,
  UNDER_MINIMUM_WARNING,
  wordCountState,
} from "@/lib/writing-exam";
import {
  findWritingTask,
  normalizeWritingTasks,
} from "@/lib/normalizeWritingTasks";
import type {
  ExamQuestion,
  WritingCriterionEvaluation,
} from "@/lib/exam-api";

describe("countWords", () => {
  it("returns 0 for empty and whitespace-only input", () => {
    expect(countWords("")).toBe(0);
    expect(countWords("   ")).toBe(0);
    expect(countWords("\n\n\t  \n")).toBe(0);
  });

  it("collapses runs of multiple spaces", () => {
    expect(countWords("the    quick     brown fox")).toBe(4);
    expect(countWords("  leading and trailing  ")).toBe(3);
  });

  it("treats newlines and tabs as word separators", () => {
    expect(countWords("first\nsecond\nthird")).toBe(3);
    expect(countWords("paragraph one\n\n\nparagraph two")).toBe(4);
    expect(countWords("tab\tseparated\twords")).toBe(3);
    expect(countWords("mixed \n\t whitespace  between")).toBe(3);
  });

  // Pinned deliberately. The exam service decides the under-length penalty with
  // Python's `len(essay_text.split())`, which also counts a standalone comma as
  // a token. A "smarter" counter here would disagree with the server about
  // whether a response was penalised.
  it("counts punctuation-only tokens as words, matching the server", () => {
    expect(countWords("hello , world")).toBe(3);
    expect(countWords("a . . . b")).toBe(5);
    expect(countWords("...")).toBe(1);
    expect(countWords("- -- ---")).toBe(3);
  });

  it("does not split punctuation attached to a word", () => {
    expect(countWords("Hello, world!")).toBe(2);
    expect(countWords("It's a well-known fact.")).toBe(4);
  });
});

describe("wordCountState", () => {
  const words = (n: number) => Array(n).fill("word").join(" ");

  it("is below target under 150 words for task 1", () => {
    expect(countWords(words(148))).toBe(148);
    expect(wordCountState(148, 1)).toBe("below");
    expect(wordCountState(149, 1)).toBe("below");
  });

  it("is met at exactly 150 words for task 1", () => {
    expect(wordCountState(150, 1)).toBe("met");
    expect(wordCountState(151, 1)).toBe("met");
  });

  it("uses a 250-word target for task 2", () => {
    expect(wordCountState(240, 2)).toBe("below");
    expect(wordCountState(249, 2)).toBe("below");
    expect(wordCountState(250, 2)).toBe("met");
  });

  it("treats an empty response as below target", () => {
    expect(wordCountState(0, 1)).toBe("below");
    expect(wordCountState(0, 2)).toBe("below");
  });

  it("drives the under-minimum warning", () => {
    expect(isUnderMinimum(149, 1)).toBe(true);
    expect(isUnderMinimum(150, 1)).toBe(false);
    expect(isUnderMinimum(249, 2)).toBe(true);
    expect(isUnderMinimum(250, 2)).toBe(false);
  });

  it("keeps the warning copy verbatim", () => {
    expect(UNDER_MINIMUM_WARNING).toBe(
      "Responses under 150 words are penalised for Task Achievement (criterion 1).",
    );
  });
});

describe("elapsedMinutes", () => {
  it("derives elapsed time from the countdown", () => {
    expect(elapsedMinutes(3600, 3600)).toBe(0);
    expect(elapsedMinutes(3600, 2400)).toBe(20);
    expect(elapsedMinutes(3600, 0)).toBe(60);
  });

  it("floors partial minutes and never goes negative", () => {
    expect(elapsedMinutes(3600, 3570)).toBe(0);
    expect(elapsedMinutes(3600, 3500)).toBe(1);
    // secondsLeft can briefly exceed the limit before the timer resyncs.
    expect(elapsedMinutes(3600, 3700)).toBe(0);
  });
});

const EVALUATIONS: WritingCriterionEvaluation[] = [
  {
    criterion: "grammar",
    band_score: 6.5,
    feedback: "Some tense inconsistencies.",
    inline_issues: [
      {
        text: "have went",
        issue_type: "Incorrect past participle",
        suggestion: "have gone",
        start_char: 10,
        end_char: 19,
      },
    ],
  },
  {
    criterion: "task_response",
    band_score: 7,
    feedback: "Covers both views.",
    inline_issues: [],
  },
  {
    criterion: "vocabulary",
    band_score: 7.5,
    feedback: "Good range.",
    inline_issues: [
      {
        text: "very big",
        issue_type: "Imprecise word choice",
        suggestion: "substantial",
        start_char: 30,
        end_char: 38,
      },
    ],
  },
  {
    criterion: "cohesion",
    band_score: 6,
    feedback: "Linking is repetitive.",
    inline_issues: [],
  },
];

describe("toEssayIssues", () => {
  it("maps the writing service's field names onto EssayHighlighter's", () => {
    const issues = toEssayIssues(EVALUATIONS);

    expect(issues).toHaveLength(2);
    expect(issues[0]).toEqual({
      text: "have went",
      issue: "Incorrect past participle",
      suggestion: "have gone",
      start: 10,
      end: 19,
      criterion: "grammar",
    });
  });

  it("carries the owning criterion onto every issue for colour coding", () => {
    const issues = toEssayIssues(EVALUATIONS);
    expect(issues.map((issue) => issue.criterion)).toEqual([
      "grammar",
      "vocabulary",
    ]);
  });

  it("tolerates criteria with no issues and a missing array", () => {
    expect(toEssayIssues([])).toEqual([]);
    expect(
      toEssayIssues([
        {
          criterion: "grammar",
          band_score: 7,
          feedback: "Fine.",
        } as WritingCriterionEvaluation,
      ]),
    ).toEqual([]);
  });
});

describe("topIssuePerCriterion", () => {
  it("returns one entry per criterion in canonical order", () => {
    const top = topIssuePerCriterion(EVALUATIONS);
    expect(top.map((item) => item.criterion)).toEqual([
      "task_response",
      "cohesion",
      "vocabulary",
      "grammar",
    ]);
  });

  it("prefers the first inline issue over the prose feedback", () => {
    const top = topIssuePerCriterion(EVALUATIONS);
    const grammar = top.find((item) => item.criterion === "grammar")!;

    expect(grammar.issue).toBe("Incorrect past participle");
    expect(grammar.suggestion).toBe("have gone");
    expect(grammar.band).toBe(6.5);
  });

  it("falls back to feedback so a criterion never disappears", () => {
    const top = topIssuePerCriterion(EVALUATIONS);
    const cohesion = top.find((item) => item.criterion === "cohesion")!;

    expect(cohesion.issue).toBe("Linking is repetitive.");
    expect(cohesion.suggestion).toBeUndefined();
  });
});

describe("formatWeightedFormula", () => {
  // The worked example from the GOA-058 ticket.
  it("renders the ticket's example exactly", () => {
    expect(formatWeightedFormula(6.5, 7, 7)).toBe(
      "(Task 1: 6.5 × 33%) + (Task 2: 7.0 × 67%) = 6.8 → Band 7.0",
    );
  });

  it("always shows one decimal place", () => {
    expect(formatWeightedFormula(6, 6, 6)).toBe(
      "(Task 1: 6.0 × 33%) + (Task 2: 6.0 × 67%) = 6.0 → Band 6.0",
    );
  });

  it("shows the server's band even when it rounds away from the raw mean", () => {
    // (6.0 + 2*7.0) / 3 = 6.666… which the exam service rounds to 6.5.
    expect(formatWeightedFormula(6, 7, 6.5)).toContain("= 6.7 → Band 6.5");
  });
});

describe("normalizeWritingTasks", () => {
  const questionSet = (questions: Record<string, unknown>[]): ExamQuestion[] => [
    {
      id: "q1",
      book_ref: "IELTS-14",
      test_number: 1,
      exam_type: "academic",
      skill_area: "writing",
      questions,
    },
  ];

  it("normalizes the ingested list shape", () => {
    const tasks = normalizeWritingTasks(
      questionSet([
        { number: 1, prompt: "Describe the chart.", instructions: "150 words." },
        { number: 2, prompt: "Discuss both views.", instructions: "250 words." },
      ]),
    );

    expect(tasks).toHaveLength(2);
    expect(tasks[0].taskNumber).toBe(1);
    expect(tasks[0].prompt).toBe("Describe the chart.");
    expect(tasks[1].taskNumber).toBe(2);
  });

  it("normalizes the task1/task2 dict shape", () => {
    const tasks = normalizeWritingTasks(
      questionSet([
        {
          task1: { prompt: "Describe the chart." },
          task2: { prompt: "Discuss both views." },
        },
      ]),
    );

    expect(tasks).toHaveLength(2);
    expect(tasks[0].taskNumber).toBe(1);
    expect(tasks[0].prompt).toBe("Describe the chart.");
    expect(tasks[1].taskNumber).toBe(2);
  });

  // Image-based evaluation is postponed (the Writing agents no longer consume
  // an image), so the UI must not read or depend on any stimulus field. A
  // payload that happens to carry one is simply ignored rather than surfaced.
  it("ignores any image/stimulus field on the payload", () => {
    const tasks = normalizeWritingTasks(
      questionSet([
        {
          number: 1,
          prompt: "Describe the chart.",
          stimulus_image_url: "https://s3.example/chart.png?sig=abc",
          image_s3_key: "writing-stimuli/chart.png",
        },
        { number: 2, prompt: "Discuss both views." },
      ]),
    );

    expect(tasks).toHaveLength(2);
    expect(tasks[0]).toEqual({
      taskNumber: 1,
      prompt: "Describe the chart.",
      instructions: undefined,
    });
    expect(Object.keys(tasks[0])).not.toContain("stimulusImageUrl");
  });

  it("degrades gracefully when there is no data, or only one task", () => {
    expect(normalizeWritingTasks(undefined)).toEqual([]);
    expect(normalizeWritingTasks([])).toEqual([]);

    const single = normalizeWritingTasks(
      questionSet([{ number: 1, prompt: "Only task one." }]),
    );
    expect(single).toHaveLength(1);
    expect(findWritingTask(single, 1)?.prompt).toBe("Only task one.");
    expect(findWritingTask(single, 2)).toBeUndefined();
  });

  it("drops entries with no usable prompt", () => {
    const tasks = normalizeWritingTasks(
      questionSet([
        { number: 1, prompt: "   " },
        { number: 2, prompt: "Real prompt." },
      ]),
    );

    expect(tasks).toHaveLength(1);
    expect(tasks[0].taskNumber).toBe(2);
  });
});
