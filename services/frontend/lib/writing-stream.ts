import { HighlightedIssue, CriterionEvaluation } from "@/lib/writing-api";

export type { HighlightedIssue, CriterionEvaluation };

export type WritingCriterionEvent = {
  type: "criterion";
  criterion: string;
  band: number;
  feedback: string;
};

export type WritingCompleteEvent = {
  type: "complete";
  essay_id: string;
  overall_band: number;
  evaluations: Record<
    string,
    {
      band: number;
      feedback: string;
    }
  >;
  evaluations_full: CriterionEvaluation[];
  improved_essay?: string;
};

export type WritingErrorEvent = {
  type: "error";
  error: string;
};

export type WritingEvent =
  | WritingCriterionEvent
  | WritingCompleteEvent
  | WritingErrorEvent;

export async function streamWritingEvaluation(
  sseUrl: string,
  onEvent: (event: WritingEvent) => void,
) {
  // credentials: "include" is required -- the SSE URL points at the Gateway
  // (/api/writing/essays/:id/evaluate), which sits behind JWT auth and a
  // RequirePaid check. Without this the httpOnly auth cookie never reaches
  // the request, the Gateway returns 401, and the caller has no way to tell
  // that apart from any other failure (BUG: writing practice hung forever
  // because this was missing and the status code was discarded).
  const response = await fetch(sseUrl, { credentials: "include" });

  if (!response.ok) {
    throw new Error(
      `Unable to start writing evaluation (status ${response.status}).`,
    );
  }

  if (!response.body) {
    throw new Error("Missing SSE response body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();

    if (done) break;

    buffer += decoder.decode(value, {
      stream: true,
    });

    const events = buffer.split("\n\n");

    buffer = events.pop() ?? "";

    for (const rawEvent of events) {
      const dataLine = rawEvent
        .split("\n")
        .find((line) => line.startsWith("data:"));

      if (!dataLine) continue;

      try {
        const payload = JSON.parse(
          dataLine.replace("data:", "").trim(),
        ) as WritingEvent;

        onEvent(payload);
      } catch (err) {
        console.error("Failed to parse writing SSE", err);
      }
    }
  }
}
