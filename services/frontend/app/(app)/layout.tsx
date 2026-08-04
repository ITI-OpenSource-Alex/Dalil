import type { ReactNode } from "react";
import { Sidebar } from "@/components/ui/sidebar";

/*
 * The shared shell for every authenticated route (chat, exam, profile,
 * checklist, speaking history). Previously each page rolled its own
 * `<div className="flex min-h-screen ..."><Sidebar/><main>...</main></div>`
 * wrapper -- exam/results/page.tsx did it 5 times, once per early return.
 * This route group (invisible in the URL) renders the Sidebar once; pages
 * keep full control over their own inner content and scroll behaviour.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-canvas text-fg">
      <Sidebar />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
