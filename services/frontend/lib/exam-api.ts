import { ExamType, SkillArea } from "@/app/types/exam";
import { throwForResponse } from "@/lib/subscription";
import { dedupe } from "@/lib/request-dedupe";
import { authenticatedFetch } from "@/lib/authenticated-fetch";

// Exam is reached through the Gateway, not directly on :8085.
//
// Calling the service directly meant shipping INTERNAL_API_KEY to the browser in
// a NEXT_PUBLIC_ variable — inlined into the client bundle and served to every
// visitor, which dissolved the boundary those internal endpoints exist to
// enforce (BUG-046). The Gateway holds that key server-side and adds JWT auth,
// rate limiting and correlation IDs on the way through.
//
// credentials: "include" is required: auth rides on HttpOnly cookies.
//
// Every non-OK response goes through throwForResponse rather than
// `throw new Error(await response.text())`. The whole /api/exam group carries
// the Gateway's paid-tier gate (GOA-059), which answers a free-tier caller
// with 403 {"error":"subscription_required"} -- so the old line put that raw
// JSON body on screen when a Free user clicked "Take Exam" on the Reading
// card. throwForResponse turns it into a SubscriptionRequiredError the UI can
// answer with the upgrade dialog, and leaves every other failure behaving
// exactly as before.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/exam`;

const headers = {
  "Content-Type": "application/json",
};

const fetchOptions: RequestInit = { credentials: "include" };

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
  // Visual exam stimulus (for example a Writing chart or Listening map).
  // `image_s3_key` is the raw object key; `image_url` is the pre-signed,
  // browser-reachable URL the exam service mints at session start
  // (services/exam/app/schemas/question.py, QuestionResponse). Both are null
  // for every non-visual task, so this is purely additive.
  image_s3_key?: string | null;
  image_url?: string | null;
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
  audio_urls?: [string, string, string, string];
  audio_url_expiry_seconds?: number;
}

export interface ExamResultResponse {
  id: string;
  session_id: string;
  user_id: string;
  skill_area: string;
  raw_score: number;
  // GOA-134: nullable. A speaking session where fewer than 3 of 4 criteria
  // completed carries no band, and the exam service now sends null rather than
  // a fabricated 0. Rendering must handle it -- `.toFixed()` on null throws.
  band_score: number | null;
  section_scores: Record<string, unknown>;
  graded_at: string;
  answer_key: Record<string, unknown>;
  per_question_result?: Record<string, import("@/app/types/reading").ReadingQuestionResult>;
  section_breakdown?: Record<string, import("@/app/types/reading").ReadingSectionBreakdown>;
  questions?: import("@/app/types/reading").RawReadingQuestion[];
}

export type ExamHistoryItem = {
  sessionId: string;
  skill: string;
  examType: string;
  bandScore: number;
  date: string;
  duration?: number | null;
  feedbackSummary?: string | null;
};

export type WeakAreas = Partial<Record<SkillArea, string>>;

export type ExamProgress = Partial<
  Record<
    "reading" | "listening" | "speaking" | "writing",
    { date: string; band: number }[]
  >
>;

// ---------------------------------------------------------------------------
// Writing exam (GOA-053 backend, surfaced by GOA-058)
// ---------------------------------------------------------------------------

/**
 * One underlined span inside the candidate's response.
 *
 * These field names are the writing service's, not the chat path's: the service
 * emits `issue_type`/`start_char`/`end_char` (services/writing/app/schemas.py)
 * whereas lib/writing-api.ts models the older `issue`/`start`/`end` shape used
 * by the chat evaluation stream. They are mapped onto EssayHighlighter's shape
 * by `toEssayIssues` in lib/writing-exam.ts rather than being renamed on either
 * side, because the chat path (GOA-043) is unit-tested against its own shape.
 *
 * Offsets are computed server-side by exact substring search against the
 * submitted text (services/writing/app/agents.py `_annotate_issues`), so they
 * are only valid against the response text exactly as it was submitted.
 */
export interface WritingInlineIssue {
  text: string;
  issue_type: string;
  suggestion: string;
  start_char: number;
  end_char: number;
}

export interface WritingCriterionEvaluation {
  criterion: "task_response" | "cohesion" | "vocabulary" | "grammar";
  band_score: number;
  feedback: string;
  improvement_tip?: string;
  word_count?: number;
  inline_issues: WritingInlineIssue[];
}

/**
 * Response to a single-task writing submit.
 *
 * `status` is "task_submitted" while only one task has landed and "submitted"
 * once both have — the exam service deliberately leaves the session
 * `in_progress` after Task 1 so the timer keeps running and Task 2 stays
 * submittable.
 */
export interface WritingSubmitResponse {
  session_id: string;
  task_number: number;
  status: "task_submitted" | "submitted";
  overall_band: number;
  word_count: number;
  penalty_flag: boolean;
  evaluations?: WritingCriterionEvaluation[];
}

export interface WritingTaskResult {
  response_text: string;
  word_count: number;
  penalty_flag: boolean;
  evaluation: {
    evaluations?: WritingCriterionEvaluation[];
    overall_band?: number;
  };
}

/**
 * Writing's result payload. Note it does NOT match ExamResultResponse — the
 * exam service branches to `_get_writing_result`, which returns a weighted
 * `overall_band` plus both task records instead of raw_score/band_score.
 */
export interface WritingResultResponse {
  session_id: string;
  user_id: string;
  skill_area: string;
  overall_band: number;
  tasks: Record<string, WritingTaskResult>;
}

export async function createSession(
  examType: ExamType,
  skillArea: SkillArea,
): Promise<CreateSessionResponse> {
  const response = await authenticatedFetch(`${API_BASE}/sessions`, {
    ...fetchOptions,
    method: "POST",
    headers,
    body: JSON.stringify({
      exam_type: mapExamType(examType),
      skill_area: mapSkillArea(skillArea),
    }),
  });

  if (!response.ok) {
    await throwForResponse(response, "exam");
  }

  return response.json();
}

/**
 * The Gateway derives the user identity from the HttpOnly-cookie JWT.
 *
 * Deduped: the Dashboard's IELTS summary and Recommendations widgets both
 * call this independently and mount at the same time -- see
 * lib/request-dedupe.ts.
 */
export async function getExamProgress(): Promise<ExamProgress> {
  return dedupe(`GET ${API_BASE}/progress`, async () => {
    const response = await authenticatedFetch(`${API_BASE}/progress`, {
      ...fetchOptions,
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
      await throwForResponse(response, "exam");
    }

    return response.json();
  });
}

export async function getExamHistory(page = 1): Promise<ExamHistoryItem[]> {
  return dedupe(`GET ${API_BASE}/history?page=${page}`, async () => {
    const response = await authenticatedFetch(`${API_BASE}/history?page=${page}`, {
      ...fetchOptions,
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      await throwForResponse(response, "exam");
    }
    return response.json();
  });
}

export async function getWeakAreas(): Promise<WeakAreas> {
  return dedupe(`GET ${API_BASE}/weak-areas`, async () => {
    const response = await authenticatedFetch(`${API_BASE}/weak-areas`, {
      ...fetchOptions,
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      await throwForResponse(response, "exam");
    }
    return response.json();
  });
}

export async function getSession(
  sessionId: string,
): Promise<ExamSessionResponse> {
  const response = await authenticatedFetch(`${API_BASE}/sessions/${sessionId}`, {
    ...fetchOptions,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    await throwForResponse(response, "exam");
  }

  return response.json();
}

export async function submitSession(
  sessionId: string,
  answers: Record<string, unknown>,
) {
  const response = await authenticatedFetch(`${API_BASE}/sessions/${sessionId}/submit`, {
    ...fetchOptions,
    method: "PUT",
    headers,
    body: JSON.stringify({
      answers,
    }),
  });

  if (!response.ok) {
    await throwForResponse(response, "exam");
  }

  return response.json();
}

/**
 * Submit one Writing task for immediate evaluation.
 *
 * Deliberately separate from `submitSession` rather than an extra optional
 * argument on it. The generic helper posts `{ answers }` and is used by the
 * Reading and Speaking paths; widening its contract so one caller can also send
 * `task_number`/`essay_text` would make a shared function's shape depend on who
 * is calling it.
 *
 * The exam service requires `task_number` and `essay_text` at the top level of
 * the body — not inside `answers` — and rejects the call with 400 otherwise
 * (SubmitAnswersRequest, services/exam/app/schemas/exam_session.py). `answers`
 * is still a required field on that model, hence the empty object.
 *
 * Submitting the same task twice is safe: the response row is UPSERTed on
 * (session_id, task_number) and its stale evaluation cleared.
 */
export async function submitWritingTask(
  sessionId: string,
  taskNumber: 1 | 2,
  essayText: string,
): Promise<WritingSubmitResponse> {
  const response = await authenticatedFetch(`${API_BASE}/sessions/${sessionId}/submit`, {
    ...fetchOptions,
    method: "PUT",
    headers,
    body: JSON.stringify({
      answers: {},
      task_number: taskNumber,
      essay_text: essayText,
    }),
  });

  if (!response.ok) {
    await throwForResponse(response, "exam");
  }

  return response.json();
}

/**
 * Fetch the combined, weighted Writing result.
 *
 * Only valid once BOTH tasks have been submitted — the exam service returns 404
 * while fewer than two response rows exist, which is why the Task 1 card is fed
 * from the submit response instead of from here.
 */
export async function getWritingResult(
  sessionId: string,
): Promise<WritingResultResponse> {
  const response = await authenticatedFetch(`${API_BASE}/sessions/${sessionId}/result`, {
    ...fetchOptions,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    await throwForResponse(response, "exam");
  }

  return response.json();
}

/**
 * Tell the backend this session is still being sat.
 *
 * The exam service sweeps in-progress sessions that stop reporting and marks
 * them abandoned, after which submit returns 403 and the attempt is lost. The
 * endpoint shipped with GOA-092 and nothing ever called it, so the sweep's only
 * input was silence (BUG-054).
 *
 * Deliberately never throws. A dropped heartbeat is not worth surfacing to a
 * candidate mid-exam, and the grace window covers several consecutive misses;
 * throwing here would put a network blip in front of someone sitting a test.
 */
export async function sendHeartbeat(sessionId: string): Promise<boolean> {
  try {
    const response = await authenticatedFetch(
      `${API_BASE}/sessions/${sessionId}/heartbeat`,
      { ...fetchOptions, method: "PATCH", headers },
    );
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Discard an active attempt on the server, not only in sessionStorage.
 *
 * A 404 means the local resume marker was already stale, so clearing it is
 * still the correct outcome. Other failures remain visible to the candidate;
 * silently clearing the marker would strand an active backend attempt again.
 */
export async function abandonSession(sessionId: string): Promise<void> {
  const response = await authenticatedFetch(`${API_BASE}/sessions/${sessionId}`, {
    ...fetchOptions,
    method: "DELETE",
    headers,
  });

  if (!response.ok && response.status !== 404) {
    await throwForResponse(response, "exam");
  }
}

export async function getResult(
  sessionId: string,
): Promise<ExamResultResponse> {
  const response = await authenticatedFetch(`${API_BASE}/sessions/${sessionId}/result`, {
    ...fetchOptions,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    await throwForResponse(response, "exam");
  }

  return response.json();
}
