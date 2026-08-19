import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ListeningExam from "@/components/listening/ListeningExam";
import type { RawReadingQuestion } from "@/app/types/reading";

const { submitListeningSession } = vi.hoisted(() => ({
  submitListeningSession: vi.fn(),
}));

vi.mock("@/lib/listening-api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/listening-api")>();
  return { ...original, submitListeningSession };
});

vi.mock("@/components/listening/LockedAudioPlayer", () => ({
  default: ({ onComplete }: { onComplete?: () => void }) => (
    <button data-testid="finish-section-audio" onClick={onComplete}>
      Finish audio
    </button>
  ),
}));

const questions: RawReadingQuestion[] = [1, 2, 3, 4].map((section) => ({
  number: section,
  prompt: `Section ${section} question`,
  question_type: "Sentence Completion",
  instructions: "Write one word.",
  passage_number: null,
  section_number: section,
}));

describe("ListeningExam lifecycle", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    submitListeningSession.mockReset();
    submitListeningSession.mockResolvedValue({
      raw_score: 0,
      band_score: 0,
      per_question_result: {},
      section_breakdown: {},
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a question-group instruction once above its question range", () => {
    const sectionQuestions: RawReadingQuestion[] = [1, 2, 3].map((number) => ({
      number,
      prompt: `Section 1 question ${number}`,
      question_type: "Notes Completion",
      instructions:
        "Complete the notes below. Write ONE WORD AND/OR A NUMBER for each answer.",
      passage_number: null,
      section_number: 1,
    }));

    render(
      <ListeningExam
        sessionId="listening-session"
        audioUrls={["one.mp3", "two.mp3", "three.mp3", "four.mp3"]}
        rawQuestions={sectionQuestions}
        onSubmitted={vi.fn()}
      />,
    );

    expect(screen.getByText("Questions 1–3")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Complete the notes below. Write ONE WORD AND/OR A NUMBER for each answer.",
      ),
    ).toHaveLength(1);
  });

  it("auto-submits saved answers when the transfer window expires", async () => {
    const onSubmitted = vi.fn();
    render(
      <ListeningExam
        sessionId="listening-session"
        audioUrls={["one.mp3", "two.mp3", "three.mp3", "four.mp3"]}
        rawQuestions={questions}
        onSubmitted={onSubmitted}
      />,
    );

    for (let section = 1; section <= 4; section += 1) {
      fireEvent.change(screen.getByPlaceholderText("Fill in the blank"), {
        target: { value: `answer-${section}` },
      });
      fireEvent.click(screen.getByTestId("finish-section-audio"));

      if (section < 4) {
        fireEvent.click(screen.getByTestId("next-section-button"));
        await act(async () => {
          vi.advanceTimersByTime(30_000);
        });
      }
    }

    await act(async () => {
      vi.advanceTimersByTime(600_000);
      await Promise.resolve();
    });

    expect(submitListeningSession).toHaveBeenCalledOnce();
    expect(submitListeningSession).toHaveBeenCalledWith("listening-session", {
      "1": "answer-1",
      "2": "answer-2",
      "3": "answer-3",
      "4": "answer-4",
    });
    expect(onSubmitted).toHaveBeenCalledOnce();
  });

  it("submits current answers when the authoritative exam clock expires", async () => {
    const onSubmitted = vi.fn();
    const view = render(
      <ListeningExam
        sessionId="listening-session"
        audioUrls={["one.mp3", "two.mp3", "three.mp3", "four.mp3"]}
        rawQuestions={questions}
        onSubmitted={onSubmitted}
        forceSubmitSignal={0}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("Fill in the blank"), {
      target: { value: "answer-1" },
    });

    view.rerender(
      <ListeningExam
        sessionId="listening-session"
        audioUrls={["one.mp3", "two.mp3", "three.mp3", "four.mp3"]}
        rawQuestions={questions}
        onSubmitted={onSubmitted}
        forceSubmitSignal={1}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(submitListeningSession).toHaveBeenCalledWith("listening-session", {
      "1": "answer-1",
    });
    expect(onSubmitted).toHaveBeenCalledOnce();
  });

  it("shows the supplied map in its section and offers map markers as choices", async () => {
    const mapQuestions: RawReadingQuestion[] = questions.map((question) =>
      question.section_number === 2
        ? {
            ...question,
            question_type: "Map Labelling",
            options: ["A", "B", "C"],
          }
        : question,
    );

    render(
      <ListeningExam
        sessionId="listening-session"
        audioUrls={["one.mp3", "two.mp3", "three.mp3", "four.mp3"]}
        rawQuestions={mapQuestions}
        stimulusImageUrl="https://images.example/minster-park.png"
        onSubmitted={vi.fn()}
      />,
    );

    expect(
      screen.queryByAltText("Map for Section 2 questions"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("finish-section-audio"));
    fireEvent.click(screen.getByTestId("next-section-button"));
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });

    expect(screen.getByAltText("Map for Section 2 questions")).toHaveAttribute(
      "src",
      "https://images.example/minster-park.png",
    );
    expect(screen.getByRole("option", { name: "Location A" })).toHaveValue("A");
  });
});
