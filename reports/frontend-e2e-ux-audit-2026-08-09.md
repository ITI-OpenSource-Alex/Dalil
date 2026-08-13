# Frontend E2E & UX Audit — 2026-08-09

## Executive verdict

The frontend has a strong foundation, and the isolated Writing, Reading, pricing, and billing flows are substantially healthier than the full-suite result suggests. The product is not ready to present its programme discovery or “all four IELTS skills” Pro promise as production-complete. The largest problem is data readiness: the live catalogue contains only seeded demo rows, not the scraped catalogue.

Only the Pro price was changed. All other items below are findings and recommendations; no implementation fixes were made.

## Evidence and test results

- Production build: **PASS**; all 30 routes, including `/exam/shell`, compiled.
- Unit suite: **453 passed, 4 failed** (457 total). All failures concern Listening state or audio locking.
- Focused E2E, one worker: **29 passed, 11 failed** (40 total).
  - Pricing/billing: **14/14 passed**, including the new **$20/month** display and simulated checkout.
  - Writing exam: **10/10 passed**.
  - Reading exam: **4/5 passed**; the highlight-isolation case submitted but did not navigate to results within the assertion window.
  - Listening exam: **0/5 reached the exam** because the spec imports plain Playwright and is redirected to login instead of using the auth fixture.
  - Checklist: **0/3 reached the checklist** because the helper expects a new user to land on `/chat`, while the product correctly sends that user to onboarding.
- Full E2E, four workers: **31 passed, 56 failed, 6 skipped**. Many failures were development-server 404s under parallel compilation. Next warned that the filesystem is slow; the successful production build proves the routes are present.
- Live RAG database: **12 programme rows**, all with `goa.internal/seed/...` source URLs; **9 Computer Science, 0 Engineering**; `documents` = **0**; `visa_requirements` = **0**. The ingestion database has no relations.
- Visual limitation: no controllable in-app browser was connected. The programme screen was reviewed from the supplied rendered text, Playwright snapshots, source, and live database/API behavior; no manual screenshots were captured.

## Findings

| Priority | What is wrong | Why it matters | What to watch for next time |
|---|---|---|---|
| **Blocker** | The live catalogue is demo data: 12 seeded programmes, zero RAG documents, and no ingested tables. | The core discovery promise is not using the “tons of programmes” that were scraped. For the tested profile, country and discipline filters leave exactly the eight cards shown. | Add a deployment data-readiness gate: minimum structured counts, non-seed source URLs, RAG chunk counts, Engineering/CS coverage, and a completed ingestion report before sign-off. |
| **Blocker** | Pro advertises “full IELTS exam simulations, all four skills,” but the Speaking exam card is explicitly **Coming soon**. | At $20/month this is a direct entitlement mismatch and the biggest trust/value problem. | Test every paid marketing bullet against an enabled, end-to-end route before publishing pricing copy. |
| **Major** | “8 programmes found” does not explain that this is the entire filtered result from a 12-row seed catalogue. One result is hard-blocked, every eligible result is only 53–60%, and a 2024-closed programme is included. | Users interpret “found” as catalogue coverage and reasonably question the scraper investment. Blocked and closed cards reduce confidence in recommendations. | Return and display metadata: catalogue total, candidates considered, eligible count, excluded/closed count, and whether the list is top-N. Separate “Eligible,” “Near matches,” and “Closed/unavailable.” |
| **Major** | Programme cards tell users to verify requirements on the official page, but provide no official programme link or data-freshness date. | The user cannot perform the verification the UI requires. Seed URLs would also expose that the data is not production-ready. | Carry `source_url` and `last_scraped_at` through the contract and show “Official programme page” plus “Last checked.” |
| **Major** | Listening state accepts `SILENCE_TICK` outside `silence_gap`, which can advance a completed section without the required click. The audio player also accepts a programmatic forward jump reported through `timeupdate` (60s remained 60s instead of snapping back to 10s). | These break exam sequencing and one-pass Listening integrity. | Reducers should reject actions invalid for the current phase. Media locks need browser-level adversarial tests for seeking, not only UI-control tests. |
| **Major** | Checklist discovery is browser-local. The detail route supplies only `programId`, so the index can store the UUID as the programme name with no university/country. Server checklists can disappear from “Your checklists” on another browser. | A long-lived application plan looks anonymous or missing even though server progress still exists. | Make the server the checklist index owner and return programme snapshots. Always render the selected programme and university in the checklist heading. |
| **Major** | Checklist copy promises financial proof, but `visa_requirements` has zero rows and the UI silently omits the phase. | The page can appear complete while lacking a critical visa/application category. | Distinguish “not required” from “data unavailable,” link evidence, and gate completeness on structured visa coverage. |
| **Major** | Several E2E tests do not represent the current app: Listening lacks auth, checklist expects `/chat` instead of onboarding, and `exam-flow` uses a placeholder token without mocking session fetches. | The suite reports feature failures before reaching the feature and can hide real regressions behind setup noise. | Centralize authenticated fixtures, complete onboarding when a test creates a new user, and label tests clearly as mocked UI vs live-stack E2E. |
| **Major** | “Current overall” averages whatever skill scores happen to exist and prints one decimal without IELTS half-band rounding. | A partial two-skill average can be mistaken for an IELTS overall band. | Require all four skills for “overall,” otherwise label it “average of completed skills”; apply the documented band-rounding rule. |
| **Minor** | The programme modal says “Ask GOA” while cards say “Ask Dalil”; its “Apply” button only builds a checklist. | Naming and action labels set conflicting expectations. | Use one product name and label the action “Build checklist” until an application flow exists. |
| **Minor** | Exam cards always describe Writing Task 1 as a report, even when General Training is selected. Results say “Official Simulation Result” despite the global non-affiliation disclaimer. | The mode switch changes behavior without updating expectations, and “Official” can overstate status. | Make card copy mode-aware and prefer “IELTS-style simulation result.” |

## Making Pro worth $20/month

1. Ship the Speaking simulation before claiming four-skill coverage, or temporarily narrow the promise.
2. Make the paid journey visibly cumulative: full exam history, correctly rounded overall band, skill trends, weaknesses, and a next-week study plan derived from results.
3. State entitlements and limits before checkout (exam attempts, speaking minutes, evaluations, CV reviews); “unlimited” must be explicit or avoided.
4. Turn feedback into actions: link each weak question type to targeted practice and show improvement between attempts.
5. Keep programme matching/checklists free as advertised, but ensure Pro-only CV review and IELTS feedback are complete, reliable, and clearly differentiated from free CV upload.

## Recommended release order

1. Populate and validate the real catalogue/RAG/visa data.
2. Fix Listening integrity and repair the test fixtures.
3. Reconcile the four-skill Pro promise and overall-band calculation.
4. Make checklist identity/index server-backed and add official source links.
5. Re-run focused specs sequentially, then stabilize the parallel suite before using it as a release gate.
