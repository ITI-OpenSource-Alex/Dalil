import { test as base, expect, type Page } from "@playwright/test";

/**
 * Programmatic sign-in for the E2E suite.
 *
 * middleware.ts guards /chat, /opportunities, /exam, /onboarding and the rest
 * on the presence of an access_token cookie. That guard used to be commented
 * out *specifically* so this suite could navigate straight to protected routes
 * without ever authenticating — which meant the routes were open in development
 * and production to keep the tests green. Seeding the cookie here is what buys
 * the guard back.
 *
 * The value is deliberately a placeholder rather than a real JWT. The Next.js
 * middleware only checks that the cookie exists (it cannot verify a signature
 * without the Gateway's secret), and these specs mock their API calls with
 * page.route, so no signed token is needed for them to be meaningful. Any spec
 * that talks to a live Gateway needs a real token from the login flow instead —
 * see signInThroughApi below.
 */
export const E2E_ACCESS_TOKEN = "e2e-placeholder-access-token";

/** Adds the session cookie to an existing context, mid-test if necessary. */
export async function seedAuthCookie(page: Page, token = E2E_ACCESS_TOKEN) {
  const { hostname } = new URL(page.url() === "about:blank" ? "http://localhost:3000" : page.url());
  await page.context().addCookies([
    {
      name: "access_token",
      value: token,
      domain: hostname,
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
      // Comfortably inside the Gateway's own 1h TTL is irrelevant here; what
      // matters is that it outlives the test run.
      expires: Math.floor(Date.now() / 1000) + 60 * 60,
    },
  ]);
}

/** Removes it again, for specs that assert the signed-out experience. */
export async function clearAuthCookie(page: Page) {
  await page.context().clearCookies({ name: "access_token" });
}

export const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8080";

/**
 * Registers a throwaway account against a live Gateway and installs its REAL
 * token, so the browser holds a session the Gateway will actually validate.
 *
 * The comment above has referred to this function ever since the placeholder
 * cookie was introduced -- "Any spec that talks to a live Gateway needs a real
 * token from the login flow instead, see signInThroughApi below" -- but it was
 * never written, and the specs that needed it kept using the placeholder.
 *
 * That stayed invisible until GOA-132 moved the Speaking WebSocket behind the
 * Gateway. Before it, the browser dialled :8082 directly with no JWT check at
 * all (BUG-029), so a fake cookie was enough to open a real socket. After it,
 * middleware.JWT rejects the placeholder at upgrade time and the panel shows
 * "Status: Error" -- the security fix working exactly as designed, surfacing as
 * three failing tests.
 *
 * Returns null when the Gateway is unreachable, so a frontend-only checkout can
 * skip rather than fail.
 */
export async function signInThroughApi(
  page: Page,
  request: import("@playwright/test").APIRequestContext,
): Promise<{ id: string; email: string; token: string } | null> {
  const email = `e2e-live-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const password = "SecurePassword123!";

  try {
    const registration = await request.post(`${GATEWAY_URL}/users`, {
      data: { email, password },
      timeout: 15000,
    });
    if (!registration.ok()) return null;
    const { id } = await registration.json();

    const login = await request.post(`${GATEWAY_URL}/auth/login`, {
      data: { email, password },
      timeout: 15000,
    });
    if (!login.ok()) return null;
    const { access_token: token } = await login.json();

    await seedAuthCookie(page, token);
    return { id, email, token };
  } catch {
    return null;
  }
}

/**
 * Drop-in replacement for `@playwright/test`'s `test`, with the session cookie
 * already installed:
 *
 *   import { test, expect } from "./fixtures/auth";
 *
 * Opt out per test with `test.use({ authenticated: false })` when the point of
 * the test is the signed-out path.
 */
export const test = base.extend<{ authenticated: boolean }>({
  authenticated: [true, { option: true }],

  // Auto fixture: runs before each test body, after the context exists.
  page: async ({ page, authenticated }, use) => {
    if (authenticated) await seedAuthCookie(page);
    await use(page);
  },
});

export { expect };

// Re-exported so a spec can switch to this module with a one-line import change
// rather than importing `test` from here and its types from somewhere else.
export type {
  Browser,
  BrowserContext,
  Locator,
  Page,
  Request,
  Response,
  Route,
  TestInfo,
} from "@playwright/test";
