import type {
  ChecklistResponse,
  FinancialRequirementsResponse,
} from "@/app/types/checklist";

// Reached through the Gateway (services/gateway/handlers/checklist.go), which
// injects X-User-ID from the JWT — same rationale as every other *-api.ts client
// here (BUG-046): no service key or user id is ever sent from the browser.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api/checklists`;

const fetchOptions: RequestInit = { credentials: "include" };

async function parseJSONOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json();
}

/** GET /api/checklists/:programId — generates on first call, reused after. */
export async function getChecklist(programId: string): Promise<ChecklistResponse> {
  const response = await fetch(
    `${API_BASE}/${encodeURIComponent(programId)}`,
    fetchOptions,
  );
  return parseJSONOrThrow<ChecklistResponse>(response);
}

/** PUT /api/checklists/:programId/items/:itemId — persists one item's checked state. */
export async function updateChecklistItem(
  programId: string,
  itemId: string,
  checked: boolean,
) {
  const response = await fetch(
    `${API_BASE}/${encodeURIComponent(programId)}/items/${encodeURIComponent(itemId)}`,
    {
      ...fetchOptions,
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ checked }),
    },
  );
  return parseJSONOrThrow(response);
}

/**
 * GET /api/checklists/:programId/financial — Financial Requirements, sourced only
 * from structured visa data (GOA-108), never the checklist's LLM path (GOA-035).
 * An empty `items` array means the program's country has no supported visa data;
 * the caller should omit the phase entirely rather than render an empty section.
 */
export async function getChecklistFinancials(
  programId: string,
): Promise<FinancialRequirementsResponse> {
  const response = await fetch(
    `${API_BASE}/${encodeURIComponent(programId)}/financial`,
    fetchOptions,
  );
  return parseJSONOrThrow<FinancialRequirementsResponse>(response);
}
