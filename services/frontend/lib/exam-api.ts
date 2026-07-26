import { ExamType, SkillArea } from "@/app/types/exam";

const API_BASE =
  process.env.NEXT_PUBLIC_EXAM_API_URL ?? "http://localhost:8085";

const INTERNAL_API_KEY = process.env.NEXT_PUBLIC_INTERNAL_API_KEY ?? "";

const headers = {
  "Content-Type": "application/json",
  "x-internal-api-key": INTERNAL_API_KEY,
};

function mapExamType(type: ExamType): "academic" | "general" {
  return type === "Academic" ? "academic" : "general";
}

function mapSkillArea(
  skill: SkillArea,
): "reading" | "listening" | "writing" | "speaking" {
  switch (skill) {
    case "Reading":
      return "reading";
    case "Listening":
      return "listening";
    case "Writing":
      return "writing";
    case "Speaking":
      return "speaking";
  }
}

export interface ExamQuestion {
  id: string;
  book_ref: string;
  test_number: number;
  exam_type: string;
  skill_area: string;
  passage_text?: string | null;
  audio_s3_key?: string | null;
  questions: Record<string, unknown>[];
}

export interface CreateSessionResponse {
  session_id: string;
  first_question_set: ExamQuestion;
}

export interface ExamSessionResponse {
  id: string;
  user_id: string;
  exam_type: string;
  skill_area: string;
  status: string;
  started_at: string;
  submitted_at?: string | null;
  time_limit_seconds: number;
  remaining_time_seconds: number;
  questions: ExamQuestion[];
}

export interface ExamResultResponse {
  id: string;
  session_id: string;
  user_id: string;
  skill_area: string;
  raw_score: number;
  band_score: number;
  section_scores: Record<string, unknown>;
  graded_at: string;
  answer_key: Record<string, unknown>;
}

export async function createSession(
  userId: string,
  examType: ExamType,
  skillArea: SkillArea,
): Promise<CreateSessionResponse> {
  const response = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      user_id: userId,
      exam_type: mapExamType(examType),
      skill_area: mapSkillArea(skillArea),
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

export async function getSession(
  sessionId: string,
): Promise<ExamSessionResponse> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

export async function submitSession(
  sessionId: string,
  answers: Record<string, unknown>,
) {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/submit`, {
    method: "PUT",
    headers,
    body: JSON.stringify({
      answers,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

export async function getResult(
  sessionId: string,
): Promise<ExamResultResponse> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/result`, {
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}
