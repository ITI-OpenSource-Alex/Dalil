/**
 * Dashboard widgets (Phase E, docs/IA-REDESIGN-PROPOSAL.md).
 *
 * Each widget is a self-contained client component that fetches its own data
 * and owns its own loading/empty/error state -- adding a new one to the
 * Dashboard is dropping an import here plus one line in
 * app/(app)/dashboard/page.tsx, not touching a shared data-fetching layer.
 */
export { WelcomeWidget } from "./welcome-widget";
export { ProgressWidget } from "./progress-widget";
export { IeltsSummaryWidget } from "./ielts-summary-widget";
export { RecentActivityWidget } from "./recent-activity-widget";
export { QuickActionsWidget } from "./quick-actions-widget";
export { PracticeShortcutsWidget } from "./practice-shortcuts-widget";
export { RecommendationsWidget } from "./recommendations-widget";
