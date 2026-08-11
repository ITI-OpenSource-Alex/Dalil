"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/ui/sidebar";
import { isExamFocusPath } from "@/lib/exam-focus";

/**
 * Authenticated app chrome wrapper. Hides Sidebar on /exam/shell so the
 * exam attempt is full-width focus mode (see
 * docs/superpowers/specs/2026-08-11-exam-focus-chrome-design.md).
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  const focusMode = isExamFocusPath(pathname);

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-fg lg:flex-row">
      {!focusMode && <Sidebar />}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
