/**
 * GOA-030 Journey 1 — register -> profile -> CV upload -> opportunity matches.
 *
 * Acceptance criterion:
 *
 *   "Register -> fill profile -> upload CV -> view opportunity matches backed by
 *    a real MastersPortal row with a non-null source URL; the match gap report
 *    includes a source-linked informational financial item when visa data
 *    exists"
 *
 * The load-bearing word is "real". The 2026-08-09 audit found the catalogue was
 * 12 seeded rows with goa.internal/seed/... URLs, and a journey that passed
 * against those would be asserting that the demo data renders. So the assertions
 * below are explicitly against a NON-seed row: a source URL on a real
 * mastersportal.com host, and dataSource === "scraped", which is the field the
 * card itself gates its "Source listing" link on.
 *
 * The financial assertion is conditional on visa data existing, exactly as the
 * AC words it -- and when it does not exist the journey says so out loud rather
 * than passing quietly. "No visa data" and "visa data not rendered" are
 * different outcomes and must not collapse.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  test,
  expect,
  step,
  setProfile,
  matchOpportunities,
  signInBrowser,
  GATEWAY_URL,
} from "./fixtures/live";

const JOURNEY = "journey-1-discovery";

test.describe("Journey 1 — discovery", () => {
  test("registers, builds a profile, uploads a CV and sees source-backed matches", async ({
    page,
    api,
    liveUser,
  }) => {
    await step(JOURNEY, "write profile through the Gateway", async () => {
      await setProfile(api, liveUser);
    });

    await step(JOURNEY, "sign the browser in", async () => {
      await signInBrowser(page, liveUser);
    });

    // ---- CV upload ---------------------------------------------------------
    // Free-tier on purpose (Phase E moved it off the paywall): a Free user can
    // hold a CV, they just cannot ask for an AI review of it.
    const cvUpload = await step(JOURNEY, "upload a CV", async () => {
      // A real PDF, because the endpoint accepts only PDF/DOC/DOCX and says so
      // with a 415. Generated once and committed rather than built here: the
      // downstream cv-processor extracts text from it, so it has to be a
      // document rather than a renamed text file.
      return await api.post(`${GATEWAY_URL}/api/writing/cv/upload`, {
        headers: { Authorization: `Bearer ${liveUser.accessToken}` },
        multipart: {
          file: {
            name: "sample-cv.pdf",
            mimeType: "application/pdf",
            buffer: readFileSync(join(__dirname, "fixtures", "sample-cv.pdf")),
          },
        },
      });
    });
    expect(
      cvUpload.ok(),
      `CV upload failed (${cvUpload.status()}): ${await cvUpload.text()}`,
    ).toBeTruthy();

    // ---- Matches, at the API boundary --------------------------------------
    // Asserted here as well as in the UI because this is where "backed by a real
    // MastersPortal row" is actually checkable: the card renders a link, but
    // only the payload proves which row it came from.
    const matches = await step(JOURNEY, "request opportunity matches", async () =>
      matchOpportunities(api, liveUser),
    );

    expect(matches.length, "no programmes matched this profile at all").toBeGreaterThan(0);

    const scraped = matches.filter(
      (program) =>
        program.dataSource === "scraped" &&
        typeof program.sourceUrl === "string" &&
        program.sourceUrl.length > 0 &&
        !program.sourceUrl.includes("goa.internal"),
    );
    expect(
      scraped.length,
      "every matched programme is seed data. The catalogue is not ingested, " +
        "so this journey would be asserting that demo rows render. " +
        `Source URLs seen: ${JSON.stringify(matches.map((p) => p.sourceUrl))}`,
    ).toBeGreaterThan(0);

    const programme = scraped[0];
    expect(programme.sourceUrl).toMatch(/^https?:\/\/(www\.)?mastersportal\.com\//);
    expect(programme.lastScrapedAt, "a scraped row with no scrape timestamp").toBeTruthy();

    // ---- The financial item, conditional exactly as the AC words it --------
    const withVisa = scraped.find(
      (program) => Array.isArray(program.visaRequirements) && program.visaRequirements.length > 0,
    );

    if (withVisa) {
      await step(JOURNEY, "check the source-linked financial item", async () => {
        const visa = withVisa.visaRequirements[0];
        expect(
          visa.source_url,
          "visa requirement carried no source URL, so the financial item it " +
            "produces cannot be traced to the page it was extracted from",
        ).toBeTruthy();
        // The AC says "official government, embassy or consular" -- assert it is
        // not a programme aggregator masquerading as one.
        expect(visa.source_url).not.toContain("mastersportal.com");
        expect(
          visa.proof_of_funds ?? visa.requirements,
          "visa row has neither proof-of-funds pathways nor requirements",
        ).toBeTruthy();
      });
    } else {
      // Deliberately not a silent pass. The AC is conditional; the report is not.
      console.warn(
        `[${JOURNEY}] no matched programme carried visa data, so the financial ` +
          "item was not asserted. This is the AC's 'when visa data exists' branch, " +
          "not a pass of the financial requirement.",
      );
      test.info().annotations.push({
        type: "conditional-branch-skipped",
        description: "financial item not asserted: no visa data for any matched programme",
      });
    }

    // ---- The same thing, through the browser -------------------------------
    // Cohesion: if a browser cannot reach it, it is not done.
    await step(JOURNEY, "render the opportunities page", async () => {
      await page.goto("/opportunities");
      // The h1 proves the authenticated shell rendered rather than a redirect
      // to /login. Matched on the real heading text -- "Opportunities" is the
      // badge above it, not a heading, so a /opportunit/i role query finds
      // nothing.
      await expect(
        page.getByRole("heading", { name: /programmes matched to your profile/i }),
      ).toBeVisible({ timeout: 60_000 });

      const sourceLinks = page.getByRole("link", { name: /source listing/i });
      await expect(
        sourceLinks.first(),
        "no 'Source listing' link rendered. The card only shows it when " +
          "dataSource === 'scraped' AND sourceUrl is set, so this means the " +
          "browser received seed rows even though the API returned scraped ones.",
      ).toBeVisible({ timeout: 60_000 });

      const href = await sourceLinks.first().getAttribute("href");
      expect(href).toMatch(/^https?:\/\/(www\.)?mastersportal\.com\//);
    });
  });
});
