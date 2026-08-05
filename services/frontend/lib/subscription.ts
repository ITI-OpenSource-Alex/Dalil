/**
 * The paid-tier gate, as the browser sees it.
 *
 * The Gateway answers a free-tier request for a paid route with
 * `403 {"error":"subscription_required","upgradeUrl":"…"}`
 * (services/gateway/middleware/subscription.go, RequirePaid). Every fetch
 * wrapper in this app used to turn that into
 * `throw new Error(await response.text())`, so clicking "Take Exam" on the
 * Reading card printed the raw JSON body into an amber banner. That is the
 * defect this module exists to remove: a deliberate product decision was
 * reaching the user dressed as a server fault.
 *
 * Orchestration emits the same marker inside the chat SSE stream as
 * `{"type":"error","error":"subscription_required"}` (app/api/chat.py), so the
 * one marker string covers both transports.
 */

export const SUBSCRIPTION_REQUIRED = "subscription_required";

/** Where the Upgrade CTA points when the Gateway does not name a URL itself. */
export const DEFAULT_UPGRADE_URL = "/#pricing";

/**
 * Thrown instead of a generic Error so call sites can branch on the *reason*
 * a request failed rather than pattern-matching a message string.
 */
export class SubscriptionRequiredError extends Error {
  readonly upgradeUrl: string;
  readonly feature?: PaidFeatureId;

  constructor(upgradeUrl?: string | null, feature?: PaidFeatureId) {
    super("This feature requires GOA Pro.");
    this.name = "SubscriptionRequiredError";
    this.upgradeUrl = upgradeUrl || DEFAULT_UPGRADE_URL;
    this.feature = feature;
  }
}

export function isSubscriptionRequiredError(
  error: unknown,
): error is SubscriptionRequiredError {
  return error instanceof SubscriptionRequiredError;
}

/** True for the SSE `error` payload orchestration sends for a gated intent. */
export function isSubscriptionRequiredMessage(message: unknown): boolean {
  return (
    typeof message === "string" &&
    message.trim().toLowerCase() === SUBSCRIPTION_REQUIRED
  );
}

/**
 * Turns a non-OK `fetch` Response into the right error type.
 *
 * Reads the body once, as text, then tries to interpret it: a 403 whose JSON
 * body carries the marker becomes a SubscriptionRequiredError; anything else
 * keeps the previous behaviour of surfacing the backend's own message. Callers
 * must not have consumed the body first.
 */
export async function throwForResponse(
  response: Response,
  feature?: PaidFeatureId,
): Promise<never> {
  const raw = await response.text().catch(() => "");

  if (response.status === 403) {
    try {
      const parsed = JSON.parse(raw) as {
        error?: unknown;
        upgradeUrl?: unknown;
      };
      if (parsed?.error === SUBSCRIPTION_REQUIRED) {
        throw new SubscriptionRequiredError(
          typeof parsed.upgradeUrl === "string" ? parsed.upgradeUrl : null,
          feature,
        );
      }
    } catch (err) {
      // A SubscriptionRequiredError raised inside the try above must not be
      // swallowed by the JSON.parse catch that surrounds it.
      if (isSubscriptionRequiredError(err)) throw err;
    }
  }

  throw new Error(raw || `Request failed with status ${response.status}`);
}

/** Same detection for axios errors, which carry a parsed `response.data`. */
export function subscriptionErrorFromAxios(
  error: unknown,
  feature?: PaidFeatureId,
): SubscriptionRequiredError | null {
  if (typeof error !== "object" || error === null || !("response" in error)) {
    return null;
  }
  const response = (error as { response?: { status?: number; data?: unknown } })
    .response;
  if (response?.status !== 403) return null;

  const data = response.data;
  if (
    typeof data === "object" &&
    data !== null &&
    (data as { error?: unknown }).error === SUBSCRIPTION_REQUIRED
  ) {
    const upgradeUrl = (data as { upgradeUrl?: unknown }).upgradeUrl;
    return new SubscriptionRequiredError(
      typeof upgradeUrl === "string" ? upgradeUrl : null,
      feature,
    );
  }
  return null;
}

/* ------------------------------------------------------------------ *
 * Feature catalogue
 *
 * One entry per route the Gateway actually gates (server.go: every
 * `subscriptionMiddleware.RequirePaid` call site). Keeping the copy here
 * rather than at each call site is what makes the upgrade experience
 * consistent — the alternative is six dialogs that each describe the paywall
 * in slightly different words.
 * ------------------------------------------------------------------ */

export type PaidFeatureId =
  | "exam"
  | "exam-reading"
  | "exam-writing"
  | "exam-listening"
  | "exam-speaking"
  | "cv-review"
  | "essay-evaluation"
  | "speaking-practice"
  | "writing-practice";

export interface PaidFeatureCopy {
  /** Shown as the dialog title. */
  title: string;
  /** One sentence on what is behind the gate. */
  description: string;
  /** What the user gets, as the dialog's bullet list. */
  benefits: string[];
}

const GENERIC: PaidFeatureCopy = {
  title: "This feature is part of GOA Pro",
  description:
    "Your account is on the Free plan, which covers programme matching, application checklists and chat. This feature belongs to the paid tier.",
  benefits: [
    "Full IELTS practice exams with scored results",
    "AI essay and CV review with inline feedback",
    "Unlimited AI conversations",
  ],
};

const FEATURE_COPY: Partial<Record<PaidFeatureId, PaidFeatureCopy>> = {
  exam: {
    title: "IELTS practice exams are part of GOA Pro",
    description:
      "Full, timed IELTS simulations and their scored results are a paid-tier feature. Your Free plan still covers programme matching, checklists and chat.",
    benefits: [
      "Timed Reading and Writing simulations from real Cambridge material",
      "Band scores with a per-question and per-criterion breakdown",
      "Progress tracking across attempts, and targeted practice advice",
    ],
  },
  "cv-review": {
    title: "CV review is part of GOA Pro",
    description:
      "Uploading a CV for AI review is a paid-tier feature. You can finish your profile and get matched without one.",
    benefits: [
      "Structured feedback on every section of your CV",
      "Rewrite suggestions aimed at admissions committees",
      "Stronger programme ranking, informed by your real experience",
    ],
  },
  "essay-evaluation": {
    title: "Essay evaluation is part of GOA Pro",
    description:
      "Scoring a Writing task against the four IELTS criteria is a paid-tier feature.",
    benefits: [
      "Band scores for Task Response, Cohesion, Vocabulary and Grammar",
      "Inline issues highlighted in your own text, with fixes",
      "An improved version of your essay to compare against",
    ],
  },
  "speaking-practice": {
    title: "Speaking practice is part of GOA Pro",
    description:
      "Live speaking sessions with an AI examiner are a paid-tier feature.",
    benefits: [
      "Real-time transcription while you speak",
      "Fluency, coherence, lexical and grammatical range scoring",
      "A reviewable history of every take",
    ],
  },
  "writing-practice": {
    title: "Writing practice is part of GOA Pro",
    description:
      "Submitting an essay for AI evaluation is a paid-tier feature.",
    benefits: [
      "Band scores against all four IELTS Writing criteria",
      "Inline corrections mapped onto your own sentences",
      "An improved rewrite to learn from",
    ],
  },
};

// The per-skill exam ids share the exam copy: the gate is the same
// `/api/exam` group, and a candidate who clicked Reading does not need a
// different explanation from one who clicked Writing.
FEATURE_COPY["exam-reading"] = FEATURE_COPY.exam;
FEATURE_COPY["exam-writing"] = FEATURE_COPY.exam;
FEATURE_COPY["exam-listening"] = FEATURE_COPY.exam;
FEATURE_COPY["exam-speaking"] = FEATURE_COPY.exam;

export function paidFeatureCopy(feature?: PaidFeatureId): PaidFeatureCopy {
  return (feature && FEATURE_COPY[feature]) || GENERIC;
}
