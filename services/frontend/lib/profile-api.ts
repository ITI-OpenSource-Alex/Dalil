import type { CurrentUser } from "@/app/types/profile";

// Reached through the Gateway, not the User service directly — same reason as
// exam-api.ts/writing-api.ts (BUG-046): calling a service directly means shipping
// its internal key to the browser. GET /api/profile (services/gateway/handlers/
// profile.go) resolves the caller's id from the JWT itself, so no id is passed here.
const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api`;

const fetchOptions: RequestInit = { credentials: "include" };

/** GET /api/profile — the authenticated user's own account + profile (BUG-047). */
export async function getMyProfile(): Promise<CurrentUser> {
  const response = await fetch(`${API_BASE}/profile`, fetchOptions);
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(message || `Request failed with status ${response.status}`);
  }
  return response.json();
}
