/**
 * GOA-030 Journey 3 — submit an essay, receive a band score with feedback.
 *
 * Acceptance criterion:
 *
 *   "Submit an essay -> receive band score evaluation with feedback"
 *
 * The subtlety is what counts as a pass. GOA-134 established the band contract:
 * an overall band is present only when at least three of the four criteria
 * completed, and when fewer complete the band is ABSENT rather than zero. A
 * journey that demanded a number would be demanding the system lie in exactly
 * the way BUG-040 did, so this asserts the contract rather than the value:
 *
 *   >= 3 criteria  ->  a band must be present and in the IELTS range
 *   <  3 criteria  ->  a band must be absent, and the journey fails on the
 *                      agent failures rather than on the missing band
 *
 * This journey is the one that found the timeout defect: the shipped default of
 * ANTHROPIC_TIMEOUT_SECONDS=25 returned "1 of 4 writing agents failed: Request
 * timed out" while .env.example had documented 120 and warned about that exact
 * value since GOA-014. See services/writing/app/config.py.
 */

import { test, expect, step, upgradeToPaid, GATEWAY_URL } from "./fixtures/live";

const JOURNEY = "journey-3-essay";

const ESSAY = `Some people believe that universities should focus on providing academic
skills, while others argue that they should prepare students for employment. In my view,
universities must do both, though the balance depends on the discipline.

Academic training develops the capacity for independent reasoning that no short vocational
course can replicate. A graduate who has learned to interrogate evidence, construct an
argument and revise a position in the face of better data carries a transferable habit of
mind that outlasts any particular technology.

However, an exclusive focus on theory leaves graduates unable to convert that reasoning
into practice. Employers consistently report that new hires understand principles but
cannot apply them under deadline pressure, in teams, with imperfect information. The most
effective universities therefore embed practical work inside academic structures rather
than bolting it on. Engineering degrees requiring an industrial placement, medical training
built around clinical rotations, and computer science courses assessed through substantial
software projects all demonstrate that rigour and employability are not opposites.

In conclusion, the dichotomy is false. Universities should teach students to think, and
give them structured opportunities to act on that thinking.`;

test.describe("Journey 3 — essay evaluation", () => {
  test("submits an essay and receives criterion feedback under the band contract", async ({
    api,
    liveUser,
  }) => {
    // Both essay routes are RequirePaid. Upgraded through the real demo billing
    // flow rather than a database write, so the subscription cache
    // invalidation and the Gateway's RequirePaid resolution are exercised too.
    await step(JOURNEY, "upgrade to the paid tier", async () => {
      await upgradeToPaid(api, liveUser);
    });

    const essayId = await step(JOURNEY, "upload the essay", async () => {
      const response = await api.post(`${GATEWAY_URL}/api/writing/essays/upload`, {
        headers: { Authorization: `Bearer ${liveUser.accessToken}` },
        multipart: { essayText: ESSAY, submissionType: "practice" },
        timeout: 120_000,
      });
      expect(
        response.ok(),
        `essay upload failed (${response.status()}): ${await response.text()}`,
      ).toBeTruthy();
      return (await response.json()).id;
    });
    expect(essayId, "upload returned no essay id").toBeTruthy();

    const body = await step(JOURNEY, "evaluate the essay", async () => {
      const response = await api.post(
        `${GATEWAY_URL}/api/writing/essays/${essayId}/evaluate`,
        {
          headers: { Authorization: `Bearer ${liveUser.accessToken}` },
          data: {},
          // Four criterion agents against a provider documented from 2.5s to
          // past 110s. The Gateway itself allows this route 6 minutes.
          timeout: 400_000,
        },
      );
      expect(
        response.ok(),
        `evaluation failed (${response.status()}): ${await response.text()}`,
      ).toBeTruthy();
      return await response.text();
    });

    await step(JOURNEY, "check criteria, feedback and the band contract", async () => {
      // A stream that reported an agent failure is a finding, not a detail --
      // it is exactly how the 25s timeout hid for months behind an otherwise
      // complete-looking evaluation.
      const agentFailure = body.match(/"detail"\s*:\s*"([^"]*agents? failed[^"]*)"/);
      expect(
        agentFailure?.[1],
        `the evaluation stream reported an agent failure: ${agentFailure?.[1]}`,
      ).toBeUndefined();

      const criteria = new Set(
        [...body.matchAll(/"criterion"\s*:\s*"([a-z_]+)"/g)].map((m) => m[1]),
      );
      expect(
        criteria.size,
        `expected four criteria, saw ${criteria.size}: ${JSON.stringify([...criteria])}`,
      ).toBe(4);

      // Feedback, not just a number. The AC says "with feedback".
      expect(
        body,
        "no per-criterion feedback text in the stream",
      ).toMatch(/"feedback"\s*:\s*"[^"]{40,}/);

      const bandMatch = body.match(/"overall_band"\s*:\s*([0-9.]+)/);
      if (criteria.size >= 3) {
        expect(
          bandMatch,
          `${criteria.size} criteria completed, so GOA-134's contract requires ` +
            "an overall band to be present, and it was absent",
        ).toBeTruthy();
        const band = Number(bandMatch![1]);
        expect(band).toBeGreaterThanOrEqual(1);
        expect(band).toBeLessThanOrEqual(9);
        // IELTS reports in half bands. A band of 7.3 means someone averaged
        // without rounding, which the 2026-08-09 audit flagged separately.
        expect(
          (band * 2) % 1,
          `overall band ${band} is not a half-band value`,
        ).toBe(0);
      } else {
        expect(
          bandMatch,
          `only ${criteria.size} criteria completed. GOA-134's contract requires ` +
            "the band to be ABSENT rather than zero in that case, and one was present.",
        ).toBeNull();
      }
    });
  });
});
