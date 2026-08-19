/**
 * GOA-030 Journey 2 — a student-visa question cites the official source.
 *
 * Acceptance criterion:
 *
 *   "Ask a student-visa question for a configured country -> verify the answer
 *    cites the fetched official government, embassy, or consular URL"
 *
 * Two decisions in here matter more than the code.
 *
 * The country is chosen at runtime from what is actually in visa_requirements,
 * read back through the Gateway's own opportunity payload rather than
 * hardcoded. A journey pinned to "Germany" passes or fails on whether one
 * ingestion run happened to cover Germany, which is not what this test is for.
 *
 * The expected host is likewise derived from the data, not written down here.
 * Asserting a literal "home-affairs.ec.europa.eu" would keep passing after a
 * re-ingest moved the source, and would fail after a legitimate one added a
 * better source -- in both cases reporting on the fixture instead of on the
 * product.
 *
 * This journey is the one that found the retrieval defect: at the shipped
 * ivfflat.probes = 1, a Germany student-visa question returned four
 * MastersPortal programme pages and zero visa documents, because the query
 * scanned one IVFFlat cluster in a hundred and the visa cluster was never among
 * them. See services/rag/app/core/config.py and perf/rag_probes_bench.py.
 */

import {
  test,
  expect,
  step,
  setProfile,
  matchOpportunities,
  GATEWAY_URL,
} from "./fixtures/live";

const JOURNEY = "journey-2-visa-citation";

/** Aggregators are not "official government, embassy or consular" sources. */
const NOT_OFFICIAL = /mastersportal\.com|studyportals|wikipedia/i;

test.describe("Journey 2 — cited visa answer", () => {
  test("answers a student-visa question citing the fetched official URL", async ({
    api,
    liveUser,
  }) => {
    await step(JOURNEY, "write profile through the Gateway", async () => {
      await setProfile(api, liveUser);
    });

    // ---- Discover which country actually has visa data ---------------------
    const { country, expectedHosts } = await step(
      JOURNEY,
      "find a configured country with ingested visa data",
      async () => {
        const programs = await matchOpportunities(api, liveUser);

        const hosts = new Set<string>();
        let found = "";
        for (const program of programs) {
          const visas = Array.isArray(program.visaRequirements) ? program.visaRequirements : [];
          for (const visa of visas) {
            if (typeof visa.source_url !== "string" || !visa.source_url) continue;
            if (NOT_OFFICIAL.test(visa.source_url)) continue;
            found ||= program.country;
            if (program.country === found) hosts.add(new URL(visa.source_url).host);
          }
        }
        return { country: found, expectedHosts: [...hosts] };
      },
    );

    // A hard failure, not a skip. The AC says "for a configured country"; if no
    // configured country has data, the ingestion handoff this journey depends
    // on has not run, and that is a real finding rather than a reason to pass.
    expect(
      country,
      "no matched programme carried an official visa source URL. " +
        "visa_requirements is empty or holds only aggregator links, so the " +
        "GOA-108/109/110 ingestion handoff has not populated this stack.",
    ).toBeTruthy();
    expect(expectedHosts.length).toBeGreaterThan(0);

    // ---- Ask, through the real chat path -----------------------------------
    const body = await step(JOURNEY, `ask about a ${country} student visa`, async () => {
      const response = await api.post(`${GATEWAY_URL}/api/chat`, {
        headers: { Authorization: `Bearer ${liveUser.accessToken}` },
        data: {
          message: `What are the student visa requirements for ${country}?`,
          sessionId: `${JOURNEY}-${Date.now()}`,
        },
        // The chat path is a real RAG query plus a real model call; measured at
        // 34-101s on this stack depending on cache state.
        timeout: 240_000,
      });
      expect(
        response.ok(),
        `chat failed (${response.status()}): ${await response.text()}`,
      ).toBeTruthy();
      return await response.text();
    });

    // ---- The citation assertion --------------------------------------------
    await step(JOURNEY, "verify an official source was cited", async () => {
      const citedHosts = new Set<string>();
      for (const match of body.matchAll(/"source_url"\s*:\s*"([^"]+)"/g)) {
        try {
          citedHosts.add(new URL(match[1]).host);
        } catch {
          // A non-URL in source_url is worth ignoring here; Journey 1 asserts
          // the field's shape.
        }
      }

      expect(
        citedHosts.size,
        `the answer cited no sources at all. Response was ${body.length} bytes.`,
      ).toBeGreaterThan(0);

      const officialCited = expectedHosts.filter((host) => citedHosts.has(host));
      expect(
        officialCited.length,
        `Asked about ${country}. Expected a citation from one of ` +
          `${JSON.stringify(expectedHosts)} -- the hosts this stack actually ` +
          `ingested visa data from -- but the answer cited ` +
          `${JSON.stringify([...citedHosts])}.\n\n` +
          "If those are all programme pages, retrieval is returning the " +
          "dominant category rather than the relevant one: check " +
          "rag_ivfflat_probes against the documents_embedding_idx lists= value.",
      ).toBeGreaterThan(0);
    });
  });
});
