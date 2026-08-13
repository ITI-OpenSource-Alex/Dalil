import type { ExamType } from "@/app/types/exam";
import type { RawReadingQuestion } from "@/app/types/reading";
import type {
  ListeningAnswers,
  ListeningStartResponse,
  ListeningSubmitResponse,
  ListeningSection,
  NormalizedListeningQuestion,
} from "@/app/types/listening";
import { normalizeReadingQuestions } from "@/lib/normalizeReadingQuestions";

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/exam`;

const headers = {
  "Content-Type": "application/json",
};

const fetchOptions: RequestInit = {
  credentials: "include",
};

function toApiExamType(examType: ExamType): "academic" | "general" {
  return examType === "Academic" ? "academic" : "general";
}

export async function startListeningSession(
  examType: ExamType,
): Promise<ListeningStartResponse> {
  const response = await fetch(
    `${API_BASE}/listening/start?exam_type=${toApiExamType(examType)}`,
    {
      ...fetchOptions,
      headers,
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

export async function submitListeningSession(
  sessionId: string,
  answers: ListeningAnswers,
): Promise<ListeningSubmitResponse> {
  const response = await fetch(`${API_BASE}/listening/${sessionId}/submit`, {
    ...fetchOptions,
    method: "PUT",
    headers,
    body: JSON.stringify({ answers }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

function listeningSectionFor(question: RawReadingQuestion): ListeningSection {
  const section = question.section_number;

  if (
    typeof section === "number" &&
    Number.isInteger(section) &&
    section >= 1 &&
    section <= 4
  ) {
    return section as ListeningSection;
  }

  // Defensive fallback for old payloads missing section_number.
  // IELTS Listening conventionally has ten questions per section.
  return Math.min(
    4,
    Math.floor((question.number - 1) / 10) + 1,
  ) as ListeningSection;
}

/**
 * Reuses Reading's question-type classification and option extraction.
 * Its `section` is deliberately overwritten: Reading has 3 passages,
 * Listening has 4 audio sections.
 */
export function normalizeListeningQuestions(
  questions: RawReadingQuestion[],
): NormalizedListeningQuestion[] {
  return normalizeReadingQuestions(questions).map((question, index) => ({
    ...question,
    section: listeningSectionFor(questions[index]),
  }));
}
