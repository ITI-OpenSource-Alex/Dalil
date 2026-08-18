const GATEWAY_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${GATEWAY_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }

  return refreshInFlight;
}

/**
 * Fetch a cookie-authenticated Gateway route and recover once from an expired
 * access JWT. The refresh cookie is HttpOnly and scoped to /auth/refresh, so
 * the browser can rotate it safely without exposing either token to JS.
 *
 * Refresh is single-flight: a heartbeat and submission that receive 401 at
 * the same moment share one rotation. Retrying rotation twice would trigger
 * the Gateway's refresh-token replay protection and sign the user out.
 */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const options: RequestInit = { ...init, credentials: "include" };
  const response = await fetch(input, options);

  if (response.status !== 401 || !(await refreshAccessToken())) {
    return response;
  }

  return fetch(input, options);
}

/** Test-only reset for module-level single-flight state. */
export function resetAuthRefreshForTests(): void {
  refreshInFlight = null;
}
