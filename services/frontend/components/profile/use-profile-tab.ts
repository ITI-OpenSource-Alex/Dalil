"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export const PROFILE_TABS = ["matches", "progress", "edit"] as const;
export type ProfileTab = (typeof PROFILE_TABS)[number];

const DEFAULT_TAB: ProfileTab = "matches";

function parseTab(value: string | null): ProfileTab {
  return PROFILE_TABS.includes(value as ProfileTab)
    ? (value as ProfileTab)
    : DEFAULT_TAB;
}

/**
 * Which profile tab is open, kept in `?tab=`.
 *
 * In the URL so a refresh, a bookmark or a shared link lands where the user
 * was. `router.replace`, not `push`: flicking between tabs is not navigation,
 * and filling the back stack with it would strand the user on their own page.
 */
export function useProfileTab() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const tab = parseTab(params.get("tab"));

  const setTab = useCallback(
    (next: ProfileTab) => {
      const search = new URLSearchParams(params.toString());
      if (next === DEFAULT_TAB) search.delete("tab");
      else search.set("tab", next);
      const query = search.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, {
        scroll: false,
      });
    },
    [params, pathname, router],
  );

  return { tab, setTab };
}
