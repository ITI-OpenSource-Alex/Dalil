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
  const response = await fetch(sseUrl);

  if (!response.ok) {
    throw new Error("Unable to start writing evaluation.");
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
