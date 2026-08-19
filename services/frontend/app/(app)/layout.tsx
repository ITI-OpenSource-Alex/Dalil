import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { UpgradeProvider } from "@/components/subscription/upgrade-dialog";
import { DalilChatProvider } from "@/components/chat/dalil-chat-provider";
import { TooltipProvider } from "@/components/ui/tooltip";

/*
 * The shared shell for every authenticated route (chat, exam, profile,
 * checklist, speaking history). Previously each page rolled its own
 * `<div className="flex min-h-screen ..."><Sidebar/><main>...</main></div>`
 * wrapper -- exam/results/page.tsx did it 5 times, once per early return.
 * This route group (invisible in the URL) renders the Sidebar once; pages
 * keep full control over their own inner content and scroll behaviour.
 *
 * UpgradeProvider wraps the whole shell so any page can turn a paid-tier
 * refusal into one consistent dialog (see lib/subscription.ts) instead of
 * each surface inventing its own banner -- or, as the exam landing page did,
 * printing the Gateway's raw 403 body.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <UpgradeProvider>
      <TooltipProvider>
        <DalilChatProvider>
          <AppShell>{children}</AppShell>
        </DalilChatProvider>
      </TooltipProvider>
    </UpgradeProvider>
  );
}
