import type { ReactNode } from "react";
import { Sidebar } from "@/components/ui/sidebar";
import { UpgradeProvider } from "@/components/subscription/upgrade-dialog";

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
      {/* flex-col below lg, flex-row at lg+: Sidebar renders two siblings --
          a sticky mobile top bar (in normal flow below lg) and the aside
          itself (position: fixed below lg, so out of flow there; lg:sticky,
          back in flow at lg+). A row container at every breakpoint put that
          mobile top bar side-by-side with the page content instead of above
          it, splitting a 375px viewport into a ~145px sidebar-ish column and
          a ~230px content column -- every authenticated page was rendering
          in barely 60% of the screen's width on mobile. */}
      <div className="flex min-h-screen flex-col bg-canvas text-fg lg:flex-row">
        <Sidebar />
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </UpgradeProvider>
  );
}
