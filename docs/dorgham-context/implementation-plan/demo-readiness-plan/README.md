# Demo Readiness Plan

## Overview

This folder breaks the GOA Demo Readiness Review's implementation plan into
individually executable documents. Each file covers exactly one task, is
self-contained (background, scope, files, implementation strategy, edge
cases, acceptance criteria, verification, dependencies, effort, risk,
status), and can be picked up, worked, and marked complete independently of
the others — subject to the dependency notes inside each file.

This documentation set does not contain any code, patches, or diffs. It is
the planning artifact to be reviewed and approved before any implementation
work begins.

## Goal

Raise the project's demo readiness from the baseline assessed in the Demo
Readiness Review — **5.4 / 10** — to the highest achievable score with
minimum engineering effort and minimum risk to the flows that already work
well (most importantly, the Reading exam).

The scope is deliberately narrow: fix what is broken or fake on the demo
path, polish what is rough, and be honest about what isn't built. Features
not needed for the demo (billing, CV review, notifications, full profile
editing, Listening/Speaking exam simulation) are explicitly out of scope
unless a task directly unblocks a demo flow.

## Overall Demo Readiness Target

| Milestone | Score |
|---|---|
| Baseline (per Demo Readiness Review) | **5.4 / 10** |
| After Phase 1 (must-do, pre-demo) | **8.2 / 10** |
| After Phase 1 + Phase 2 (nice-to-have) | **8.8 / 10** |

Phase 3 items are explicitly deferred past the demo and are not counted
toward the readiness score above.

## Phases

- **Phase 1 — Must be completed before the demo.** Fixes every flow that
  currently errors, hangs, crashes, or shows fabricated/placeholder content
  on the primary demo path. Ordered so the highest-uncertainty item (Reading
  exam question data) is resolved first.
- **Phase 2 — Nice improvements.** Closes remaining rough edges (dead
  endpoints, missing input caps, cosmetic dashboard data, auth middleware)
  that raise polish and reliability but are not launch-blocking for the
  demo.
- **Phase 3 — Can wait until after the demo.** Larger, higher-risk, or
  genuinely out-of-scope work (merging the Writing exam UI branch, profile
  persistence, billing, Listening/Speaking exam builds, etc.). Documented
  for completeness, not scheduled against the demo date.

## Recommended Execution Order

Work Phase 1 documents in numeric order — the numbering already reflects
execution priority and dependency order (e.g., real user identity must land
before the opportunity-matching seed can be verified end-to-end). Within
Phase 2 and Phase 3, task order is ROI-ordered but tasks are independent
enough to reorder if needed; check each task's **Dependencies** section
before starting it out of order.

1. [01 — Reading Exam Question Data](01-reading-exam-data.md)
2. [02 — Writing Practice Infinite Spinner Fix](02-writing-practice-fix.md)
3. [03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md)
4. [04 — Real User Identity Wiring](04-real-user-identity.md)
5. [05 — Landing Page Components](05-landing-page.md)
6. [06 — Sidebar Navigation Cleanup](06-sidebar-navigation.md)
7. [07 — Chat Opportunity Card Layout Fix](07-chat-layout-fix.md)
8. [08 — Exam Placeholder Replacement](08-exam-placeholders.md)
9. [09 — Remove Fabricated Results Content](09-remove-fake-results-content.md)
10. [10 — Error Boundaries and Crash Guards](10-error-boundaries-crash-guards.md)
11. [11 — Loading and Error State Polish](11-loading-error-states.md)
12. [Phase 2 — Nice Improvements](phase-2.md)
13. [Phase 3 — Post-Demo Backlog](phase-3.md)

## Estimated Total Effort

| Phase | Implementation | Testing | Notes |
|---|---|---|---|
| Phase 1 (docs 01–11) | ≈ 10.3 h | ≈ 3 h (incl. integration pass) | Includes 1 medium-risk item (real user identity) |
| Phase 2 | ≈ 4.5 h | ≈ 1 h (regression pass) | Includes 1 medium-risk item (route protection) |
| Dress rehearsals & cross-breakpoint check | — | ≈ 2 h | Two full cold-start runs + responsive check |
| **Phase 1 + Phase 2 total** | **≈ 14.8 h** | **≈ 4.5 h** | **≈ 19.3 h total, ~2.5 working days** |
| Phase 3 | Not scheduled | Not scheduled | Post-demo backlog only |

If only one working day is available, execute Phase 1 documents 01–09 and
defer 10 and 11, accepting the residual crash/polish risk documented in
those two files.

## Progress Checklist

Status is tracked per-document in each file's own **Status** section
(default: `Not Started`). This checklist mirrors that state for a
one-glance view — update both when a task's status changes.

### Phase 1 — Must be completed before the demo

- [x] [01 — Reading Exam Question Data](01-reading-exam-data.md) — *Completed*
- [x] [02 — Writing Practice Infinite Spinner Fix](02-writing-practice-fix.md) — *Completed*
- [x] [03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md) — *Completed*
- [x] [04 — Real User Identity Wiring](04-real-user-identity.md) — *Completed*
- [x] [05 — Landing Page Components](05-landing-page.md) — *Completed*
- [x] [06 — Sidebar Navigation Cleanup](06-sidebar-navigation.md) — *Completed*
- [x] [07 — Chat Opportunity Card Layout Fix](07-chat-layout-fix.md) — *Completed*
- [x] [08 — Exam Placeholder Replacement](08-exam-placeholders.md) — *Completed*
- [x] [09 — Remove Fabricated Results Content](09-remove-fake-results-content.md) — *Completed*
- [x] [10 — Error Boundaries and Crash Guards](10-error-boundaries-crash-guards.md) — *Completed*
- [x] [11 — Loading and Error State Polish](11-loading-error-states.md) — *Completed*

### Phase 2 — Nice Improvements

- [ ] [Phase 2 — Nice Improvements](phase-2.md) (8 sub-tasks, see file) — *Not Started*

### Phase 3 — Post-Demo Backlog

- [ ] [Phase 3 — Post-Demo Backlog](phase-3.md) (15 sub-tasks, see file) — *Not Started*

## Source

This plan is derived from the GOA Demo Readiness Review conducted against
branch `feature/GOA-035-application-checklist`. All file paths, line
references, and technical claims in the individual documents were verified
against the actual repository contents at review time (not inferred from
requirements documentation alone).
