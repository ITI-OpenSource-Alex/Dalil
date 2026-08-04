"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  AudioLines,
  ChevronUp,
  FileText,
  GraduationCap,
  ListChecks,
  LogOut,
  Menu,
  MessageSquare,
  Sparkles,
  Target,
  User as UserIcon,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { authApi } from "@/lib/api";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { Badge, Button, Icon } from "@/components/ui";
import { Wordmark } from "@/components/marketing/wordmark";

// Derives up to 2 uppercase initials from an email's local part (the
// segment before "@") for the avatar badge -- CurrentUser carries no
// separate display name, only an email.
function initialsFromEmail(email: string): string {
  const localPart = email.split("@")[0] ?? "";
  const letters = localPart.replace(/[^a-zA-Z]/g, "");
  return (letters.slice(0, 2) || email.slice(0, 2) || "?").toUpperCase();
}

// href: null marks an entry as genuinely unavailable -- rendered as an inert
// badge rather than a Link, with `unavailableReason` as the explicit,
// visible reason (not just a hover tooltip). Opportunity search and the
// application checklist *are* implemented, but only inline inside Chat (see
// chat-shell.tsx and /checklist/[programId]) -- there is no standalone page
// for either yet, so they link to /chat with a "In Chat" badge instead of
// being marked unavailable, and `linksElsewhere: true` keeps them from
// double-highlighting alongside the Chat item itself.
// matchStrategy: "prefix" is opt-in, only for routes with real child routes
// that should share the highlight (/exam/shell, /exam/results under IELTS;
// /speaking/history/[id] under Speaking History) -- every other route
// matches exactly, so a route like /profile is never marked active while
// merely prefixed by another route's path.
const NAV_ITEMS: {
  label: string;
  icon: LucideIcon;
  href: string | null;
  matchStrategy?: "exact" | "prefix";
  linksElsewhere?: boolean;
  elsewhereBadge?: string;
  unavailableReason?: string;
}[] = [
  { label: "Chat", icon: MessageSquare, href: "/chat" },
  {
    label: "Opportunities",
    icon: Target,
    href: "/chat",
    linksElsewhere: true,
    elsewhereBadge: "In Chat",
  },
  {
    label: "Checklists",
    icon: ListChecks,
    href: "/chat",
    linksElsewhere: true,
    elsewhereBadge: "In Chat",
  },
  { label: "IELTS", icon: GraduationCap, href: "/exam", matchStrategy: "prefix" },
  {
    label: "Speaking History",
    icon: AudioLines,
    href: "/speaking/history",
    matchStrategy: "prefix",
  },
  {
    label: "CV Review",
    icon: FileText,
    href: null,
    unavailableReason: "Requires GOA Pro — coming soon",
  },
  { label: "Profile", icon: UserIcon, href: "/profile" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  // GOA-035/BUG-047: the account badge previously always showed a
  // hardcoded "Lina Ahmadi" persona regardless of who was actually logged
  // in. The Sidebar renders on every authenticated page, so this issues
  // its own GET /api/profile per page load -- an accepted, cheap
  // duplication (see doc 04) rather than a shared context provider.
  const { user, status: profileStatus } = useCurrentUser();
  const identityLoading =
    profileStatus === "loading" || profileStatus === "idle";

  // Close the drawer whenever the route changes
  useEffect(() => {
    setIsOpen(false);
  }, [pathname]);

  // Prevent background scroll when the mobile drawer is open
  useEffect(() => {
    document.body.style.overflow = isOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  return (
    <>
      {/* Mobile top bar with hamburger trigger */}
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-surface px-4 py-3 lg:hidden print:hidden">
        <Link href="/" className="flex items-center gap-2.5">
          <Wordmark />
        </Link>
        <Button
          variant="ghost"
          size="sm"
          iconOnly
          onClick={() => setIsOpen(true)}
          aria-label="Open menu"
        >
          <Icon icon={Menu} size="sm" />
        </Button>
      </div>

      {/* Backdrop overlay (mobile only, shown when drawer is open) */}
      {isOpen && (
        <div
          onClick={() => setIsOpen(false)}
          className="fixed inset-0 z-40 bg-sage-950/40 lg:hidden"
          aria-hidden="true"
        />
      )}

      {/* Sidebar / Drawer */}
      <aside
        className={cn(
          "fixed top-0 left-0 z-50 flex h-screen w-64 shrink-0 select-none flex-col justify-between",
          "border-r border-border bg-surface p-5 font-sans",
          "transition-transform duration-300 ease-in-out",
          "lg:sticky lg:translate-x-0 print:hidden",
          isOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="space-y-8">
          {/* Brand Header (desktop only, mobile has its own top bar) */}
          <Link href="/" className="hidden items-center gap-2.5 px-2 lg:flex">
            <Wordmark />
          </Link>

          {/* Mobile drawer header with close button */}
          <div className="flex items-center justify-between px-2 lg:hidden">
            <Link href="/">
              <Wordmark />
            </Link>
            <Button
              variant="ghost"
              size="sm"
              iconOnly
              onClick={() => setIsOpen(false)}
              aria-label="Close menu"
            >
              <Icon icon={X} size="sm" />
            </Button>
          </div>

          {/* Navigation Items */}
          <nav aria-label="Main" className="space-y-1">
            {NAV_ITEMS.map((item) => {
              if (!item.href) {
                const reason = item.unavailableReason ?? `${item.label} — coming soon`;
                return (
                  <div
                    key={item.label}
                    aria-disabled="true"
                    title={reason}
                    className="flex cursor-not-allowed items-center justify-between gap-3 rounded-full px-3.5 py-2.5 text-sm font-medium text-fg-subtle select-none"
                  >
                    <span className="flex items-center gap-3">
                      <Icon icon={item.icon} size="sm" className="text-fg-subtle/70" />
                      <span>{item.label}</span>
                    </span>
                    <Badge tone="neutral" size="sm" pill>
                      Soon
                    </Badge>
                  </div>
                );
              }

              const isActive =
                !item.linksElsewhere &&
                (item.matchStrategy === "prefix"
                  ? pathname === item.href || pathname.startsWith(`${item.href}/`)
                  : pathname === item.href);

              return (
                <Link
                  key={item.label}
                  href={item.href}
                  onClick={() => setIsOpen(false)}
                  aria-current={isActive ? "page" : undefined}
                  title={item.linksElsewhere ? `${item.label} — inside Chat` : undefined}
                  className={cn(
                    "flex items-center justify-between gap-3 rounded-full px-3.5 py-2.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-brand-subtle font-semibold text-brand-fg"
                      : "text-fg-muted hover:bg-canvas-subtle hover:text-fg",
                  )}
                >
                  <span className="flex items-center gap-3">
                    <Icon icon={item.icon} size="sm" />
                    <span>{item.label}</span>
                  </span>
                  {item.elsewhereBadge && (
                    <Badge tone="info" size="sm" pill>
                      {item.elsewhereBadge}
                    </Badge>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Bottom Pro Callout & User Menu */}
        <div className="space-y-4">
          {!identityLoading && user && !user.profile && (
            <Link
              href="/onboarding"
              className="flex items-start gap-2.5 rounded-panel border border-warning-border bg-warning-subtle p-4 transition-colors hover:bg-warning-subtle/80"
            >
              <Icon icon={AlertCircle} size="sm" className="mt-0.5 shrink-0 text-warning-fg" />
              <span>
                <span className="block text-sm font-semibold text-warning-fg">
                  Complete Profile
                </span>
                <span className="mt-0.5 block text-[11px] leading-normal text-warning-fg/80">
                  Finish onboarding to unlock programme matching.
                </span>
              </span>
            </Link>
          )}

          <div className="space-y-3 rounded-panel border border-brand-border bg-brand-subtle p-4">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-brand-fg">
              <Icon icon={Sparkles} size="xs" />
              <span>Free plan</span>
            </div>
            <div>
              <h4 className="text-sm leading-tight font-bold text-fg">
                Unlock GOA Pro
              </h4>
              <p className="mt-1 text-[11px] leading-normal text-fg-muted">
                Unlimited AI, CV review, IELTS scoring.
              </p>
            </div>
            <Button size="sm" trailingIcon={ArrowRight}>
              Upgrade
            </Button>
          </div>

          <UserMenu
            user={user}
            identityLoading={identityLoading}
          />
        </div>
      </aside>
    </>
  );
}

function UserMenu({
  user,
  identityLoading,
}: {
  user: { email: string } | null;
  identityLoading: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: PointerEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  async function handleLogout() {
    setOpen(false);
    try {
      await authApi.logout();
    } catch {
      // Best-effort: even if the network call fails, the client still treats
      // the session as ended rather than stranding the user on a dead menu.
    } finally {
      router.push("/login");
      router.refresh();
    }
  }

  return (
    <div ref={containerRef} className="relative border-t border-border pt-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex w-full items-center gap-3 rounded-control px-2 py-2 text-left transition-colors hover:bg-canvas-subtle"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-forest-800 text-xs font-bold text-white">
          {identityLoading ? "···" : user ? initialsFromEmail(user.email) : "?"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-bold text-fg">
            {identityLoading ? "Loading…" : (user?.email ?? "Not signed in")}
          </span>
        </span>
        <Icon
          icon={ChevronUp}
          size="xs"
          className={cn("text-fg-subtle transition-transform", !open && "rotate-180")}
        />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Account"
          className="absolute bottom-full left-0 z-10 mb-2 w-full rounded-panel border border-border bg-surface-raised p-1.5 shadow-e2"
        >
          <Link
            role="menuitem"
            href="/profile"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-control px-3 py-2 text-sm text-fg transition-colors hover:bg-canvas-subtle"
          >
            <Icon icon={UserIcon} size="sm" />
            Profile
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-control px-3 py-2 text-left text-sm text-fg transition-colors hover:bg-canvas-subtle"
          >
            <Icon icon={LogOut} size="sm" />
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
