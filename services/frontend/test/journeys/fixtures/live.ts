/**
 * GOA-030 — harness for the live-stack journey suite.
 *
 * These journeys are the opposite of the specs in test/e2e/. Those mock their
 * backend with page.route and seed a placeholder cookie that the Next.js
 * middleware accepts because it only checks for presence; they are UI contract
 * tests and they are useful as that. Nothing here mocks anything. Every request
 * goes to a running Gateway, every account is registered through the real
 * registration endpoint, and every assertion is on bytes a browser actually
 * received.
 *
 * Three constraints shaped this file, all of them discovered by running the
 * stack rather than by reading it:
 *
 * 1. The Gateway rate-limits /api to 60 requests per user per minute. A suite
 *    that shared one account across journeys exhausted that and started
 *    reporting 429s as feature failures -- tests/e2e/README.md records the same
 *    lesson from GOA-039. So: one freshly registered account per journey.
 *
 * 2. Journeys 3 and 4 touch RequirePaid routes. The demo billing endpoints are
 *    deliberately NOT paywalled (a paywall on the routes that sell the paid
 *    tier would be a closed loop), so a test can upgrade its own throwaway
 *    account through the real flow instead of writing to the database.
 *
 * 3. Onboarding is not optional. A newly registered user is sent to
 *    /onboarding, and several journeys need a profile to exist before they mean
 *    anything -- an opportunity match against an empty profile is not a match.
 */

import { test as base, expect, request as playwrightRequest } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";
import { STEP_ATTACHMENT } from "./metrics";

export const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8080";

export interface LiveUser {
  id: string;
  email: string;
  password: string;
  accessToken: string;
}

const PASSWORD = "SecurePassword123!";

/** Registers and signs in a brand-new account against the real Gateway. */
export async function createLiveUser(api: APIRequestContext): Promise<LiveUser> {
  // Date.now() alone collides under four parallel workers, which register
  // within the same millisecond often enough to matter.
  const email = `goa030-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;

  const registration = await api.post(`${GATEWAY_URL}/users`, {
    data: { email, password: PASSWORD },
  });
  expect(
    registration.ok(),
    `registration failed (${registration.status()}): ${await registration.text()}`,
  ).toBeTruthy();
  const { id } = await registration.json();

  const login = await api.post(`${GATEWAY_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(
    login.ok(),
    `login failed (${login.status()}): ${await login.text()}`,
  ).toBeTruthy();
  const { access_token: accessToken } = await login.json();

  return { id, email, password: PASSWORD, accessToken };
}

/**
 * Upgrades an account to the paid tier through the real demo billing flow.
 *
 * Deliberately not a database write. The point of driving create-checkout ->
 * demo/confirm is that the subscription cache invalidation, the User service
 * state transition and the Gateway's RequirePaid resolution are all exercised;
 * a direct UPDATE would leave every one of those untested and still turn the
 * journey green.
 */
export async function upgradeToPaid(api: APIRequestContext, user: LiveUser): Promise<void> {
  const checkout = await api.post(`${GATEWAY_URL}/api/billing/create-checkout`, {
    headers: { Authorization: `Bearer ${user.accessToken}` },
    data: { returnUrl: "http://localhost:3000/billing/success" },
  });
  expect(
    checkout.ok(),
    `create-checkout failed (${checkout.status()}): ${await checkout.text()}`,
  ).toBeTruthy();

  const { url } = await checkout.json();
  const token = new URL(url).searchParams.get("session");
  expect(token, `no session token in checkout url: ${url}`).toBeTruthy();

  const confirm = await api.post(`${GATEWAY_URL}/api/billing/demo/confirm`, {
    headers: { Authorization: `Bearer ${user.accessToken}` },
    // 4242... is the demo table's success card. 4000000000009995 declines.
    data: { token, cardNumber: "4242424242424242" },
  });
  expect(
    confirm.ok(),
    `demo confirm failed (${confirm.status()}): ${await confirm.text()}`,
  ).toBeTruthy();
  expect((await confirm.json()).status).toBe("succeeded");
}

/** Writes a profile through the Gateway, the way the onboarding wizard does. */
export async function setProfile(
  api: APIRequestContext,
  user: LiveUser,
  overrides: Record<string, unknown> = {},
): Promise<void> {
  const response = await api.put(`${GATEWAY_URL}/api/profile`, {
    headers: { Authorization: `Bearer ${user.accessToken}` },
    data: {
      degreeLevel: "bachelor",
      gpa: 3.6,
      gpaScale: "4.0",
      ieltsScore: 7.0,
      targetCountries: ["Germany"],
      fieldOfStudy: "Computer Science",
      ects: 180,
      workExperienceYears: 1,
      ...overrides,
    },
  });
  expect(
    response.ok(),
    `profile update failed (${response.status()}): ${await response.text()}`,
  ).toBeTruthy();
}

/**
 * Requests opportunity matches, tolerating the documented replication delay.
 *
 * The profile is written to the User service, which publishes it to SQS; RAG
 * consumes it into local_user_profiles and only then can score anything. Until
 * that lands, /match answers **425 Too Early, "Profile not yet replicated.
 * Please retry."** -- a deliberate contract, not a fault
 * (services/rag/app/services/scoring.py:172).
 *
 * So this retries 425 specifically and nothing else. A 500 or a 429 fails
 * immediately, because those are not "not yet" and retrying them would turn a
 * real defect into a slow pass. The bound matters too: if replication never
 * happens, the SQS consumer is down and the journey must say so.
 */
export async function matchOpportunities(
  api: APIRequestContext,
  user: LiveUser,
  timeoutMs = 60_000,
): Promise<Array<Record<string, any>>> {
  const deadline = Date.now() + timeoutMs;
  let lastStatus = 0;

  while (Date.now() < deadline) {
    const response = await api.post(`${GATEWAY_URL}/api/opportunities/query`, {
      headers: { Authorization: `Bearer ${user.accessToken}` },
      data: {},
      timeout: 120_000,
    });
    lastStatus = response.status();

    if (response.ok()) {
      return (await response.json()).programs as Array<Record<string, any>>;
    }
    if (lastStatus !== 425) {
      throw new Error(
        `opportunity match failed (${lastStatus}): ${await response.text()}`,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error(
    `profile never replicated to RAG within ${timeoutMs}ms (last status ${lastStatus}). ` +
      "The user-events SQS consumer in the RAG service is the thing to check.",
  );
}

/** Installs the REAL session cookie so the browser is genuinely signed in. */
export async function signInBrowser(page: Page, user: LiveUser): Promise<void> {
  await page.context().addCookies([
    {
      name: "access_token",
      value: user.accessToken,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
      expires: Math.floor(Date.now() / 1000) + 60 * 60,
    },
  ]);
}

/**
 * Deletes the account the journey created.
 *
 * Best-effort on purpose: a failed teardown must not turn a passing journey
 * red, and must not mask the real failure of a failing one. It is reported,
 * not thrown.
 */
export async function deleteLiveUser(api: APIRequestContext, user: LiveUser): Promise<void> {
  try {
    const response = await api.delete(`${GATEWAY_URL}/users/${user.id}/account`, {
      headers: { Authorization: `Bearer ${user.accessToken}` },
      // Erasure is password-confirmed, so a stolen token alone cannot delete an
      // account. Omitting it 422s -- which is the endpoint behaving correctly,
      // not a teardown that can be skipped.
      data: { confirmPassword: user.password },
    });
    if (!response.ok()) {
      console.warn(`teardown: could not delete ${user.email} (${response.status()})`);
    }
  } catch (error) {
    console.warn(`teardown: could not delete ${user.email}: ${error}`);
  }
}

/**
 * Times one named action, attaches it to the Playwright report, and records it
 * as goa_e2e_step_duration_ms{journey,step}.
 *
 * The AC asks for step-level timing as a CloudWatch custom metric. There is no
 * CloudWatch on this project, so the metric goes to a Prometheus Pushgateway
 * with the same name and the same two labels -- see fixtures/metrics.ts.
 */
export async function step<T>(
  journey: string,
  name: string,
  body: () => Promise<T>,
): Promise<T> {
  const started = Date.now();
  try {
    return await base.step(name, body);
  } finally {
    // Attached to the test result rather than pushed from here.
    //
    // Specs run in worker PROCESSES and the reporter runs in the main one, so a
    // module-level array in the worker is invisible to the reporter -- which is
    // exactly how the first version of this silently pushed nothing. An
    // attachment is the supported worker-to-reporter channel.
    //
    // Best-effort: a failure to record a timing must never fail a journey.
    try {
      await base.info().attach(STEP_ATTACHMENT, {
        contentType: "application/json",
        body: Buffer.from(
          JSON.stringify({
            journey,
            step: name,
            durationMs: Date.now() - started,
            at: new Date().toISOString(),
          }),
        ),
      });
    } catch {
      /* no testInfo (called outside a test), or attachment rejected */
    }
  }
}

/**
 * Playwright's `test` with a live account already provisioned.
 *
 * `liveUser` is worker-scoped rather than test-scoped: registering, onboarding
 * and upgrading costs several Gateway calls, and repeating them per test inside
 * a journey would spend the 60/min budget on setup instead of on the journey.
 */
export const test = base.extend<{
  api: APIRequestContext;
  liveUser: LiveUser;
}>({
  api: async ({}, use) => {
    const context = await playwrightRequest.newContext();
    await use(context);
    await context.dispose();
  },

  liveUser: async ({ api }, use) => {
    const user = await createLiveUser(api);
    await use(user);
    await deleteLiveUser(api, user);
  },
});

export { expect };
export type { APIRequestContext, Page };
