import { PageContainer } from "@/components/ui";
import {
  IeltsSummaryWidget,
  PracticeShortcutsWidget,
  ProgressWidget,
  QuickActionsWidget,
  RecentActivityWidget,
  RecommendationsWidget,
  WelcomeWidget,
} from "@/components/dashboard";

/**
 * The user's home after onboarding (Phase E, docs/IA-REDESIGN-PROPOSAL.md),
 * replacing the temporary redirect to /opportunities. A grid of independent
 * widgets, each owning its own data and its own loading/empty state -- see
 * components/dashboard/index.ts for how to add another one.
 */
export default function DashboardPage() {
  return (
    <PageContainer size="xl">
      <div className="space-y-6">
        <WelcomeWidget />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <IeltsSummaryWidget />
            <RecentActivityWidget />
            <QuickActionsWidget />
          </div>
          <div className="space-y-6">
            <ProgressWidget />
            <PracticeShortcutsWidget />
          </div>
        </div>

        <RecommendationsWidget />
      </div>
    </PageContainer>
  );
}
