import type { CurrentUser } from "@/app/types/profile";
import { dedupe } from "@/lib/request-dedupe";

// Reached through the Gateway, not the User service directly — same reason as
// exam-api.ts/writing-api.ts (BUG-046): calling a service directly means shipping
// its internal key to the browser. GET /api/profile (services/gateway/handlers/
// profile.go) resolves the caller's id from the JWT itself, so no id is passed here.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api`;

const fetchOptions: RequestInit = { credentials: "include" };

/** GET /api/profile — the authenticated user's own account + profile (BUG-047).
 *
 * Deduped: the sidebar and (as of the Dashboard) two of its widgets each call
 * this independently, and on first mount all three fire before any of them
 * has a response -- see lib/request-dedupe.ts.
 */
export async function getMyProfile(): Promise<CurrentUser> {
  return dedupe(`GET ${API_BASE}/profile`, async () => {
    const response = await fetch(`${API_BASE}/profile`, fetchOptions);
    if (!response.ok) {
      const message = await response.text().catch(() => "");
      throw new Error(message || `Request failed with status ${response.status}`);
    }
    return response.json();
  });
}
