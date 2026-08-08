"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  AudioLines,
  ChevronUp,
  FileText,
  GraduationCap,
  LayoutDashboard,
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
import { DEFAULT_UPGRADE_URL } from "@/lib/subscription";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { isProfileComplete } from "@/app/types/profile";
import { emailInitials } from "@/lib/user-display";
import { Badge, Button, Icon } from "@/components/ui";
import { Wordmark } from "@/components/marketing/wordmark";

// href: null marks an entry as genuinely unavailable -- rendered as an inert
// badge rather than a Link, with `unavailableReason` as the explicit,
// visible reason (not just a hover tooltip).
//
// matchStrategy: "prefix" is opt-in, only for routes with real child routes
// that should share the highlight (/exam/shell, /exam/results under IELTS) --
// every other route matches exactly, so a route like /profile is never marked
// active while merely prefixed by another route's path.
//
// `children` are sub-routes rendered indented beneath their parent, and only
// while that section is the active one. Speaking History used to sit at the
// top level as a peer of Chat and IELTS, which put a *history view* of one
// practice mode at the same altitude as the product's primary sections --
// fixed by nesting it under a standalone Speaking section. Phase D
// generalises that fix: Speaking and Writing are now peers under one
// Practice section (both were previously reachable only via Chat's toolbar
// buttons, Writing with no sidebar presence at all), each with its own
// Practice + History children. Opportunities and Checklists likewise stop
// pointing at /chat with an "In Chat" badge -- both now have their own pages.
interface NavItem {
  label: string;
  icon: LucideIcon;
  href: string | null;
  matchStrategy?: "exact" | "prefix";
  unavailableReason?: string;
  /**
   * Extra path prefixes that should also light this item up. Needed because
   * the checklist detail view lives at the pre-existing /checklist/:programId
   * (linked from chat and covered by e2e specs) while its new index is
   * /checklists -- renaming the former to tidy the sidebar would be the tail
   * wagging the dog.
   */
  alsoActiveFor?: string[];
  children?: { label: string; href: string; matchStrategy?: "exact" | "prefix" }[];
}

const NAV_ITEMS: NavItem[] = [
  // Phase E (docs/IA-REDESIGN-PROPOSAL.md): the user's home after
  // onboarding, replacing the temporary redirect to /opportunities.
  { label: "Dashboard", icon: LayoutDashboard, href: "/dashboard" },
  { label: "Chat", icon: MessageSquare, href: "/chat" },
  { label: "IELTS Exam", icon: GraduationCap, href: "/exam", matchStrategy: "prefix" },
  {
    // Phase D (docs/IA-REDESIGN-PROPOSAL.md): a standalone section, no
    // longer reachable only by opening Chat and finding the right toolbar
    // button. "Speaking" used to sit here as its own top-level item with a
    // single History child; Writing had no sidebar presence at all. Both
    // skills are peers under Practice now, each with Practice + History.
    label: "Practice",
    icon: AudioLines,
    href: "/practice",
    matchStrategy: "prefix",
    children: [
      { label: "Speaking Practice", href: "/practice/speaking" },
      {
        label: "Speaking History",
        href: "/practice/speaking/history",
        matchStrategy: "prefix",
      },
      { label: "Writing Practice", href: "/practice/writing" },
      {
        label: "Writing History",
        href: "/practice/writing/history",
        matchStrategy: "prefix",
      },
    ],
  },
  { label: "Opportunities", icon: Target, href: "/opportunities" },
  {
    label: "Checklists",
    icon: ListChecks,
    href: "/checklists",
    matchStrategy: "prefix",
    alsoActiveFor: ["/checklist/"],
  },
  // Phase E: standalone page, upload is free-tier, AI review remains paid
  // (surfaced by the upgrade dialog on the page itself, not by hiding the
  // nav entry -- href: null is for routes that don't exist yet, not for
  // paid features, see the comment above NavItem).
  { label: "CV Review", icon: FileText, href: "/cv-review" },
  { label: "Profile", icon: UserIcon, href: "/profile" },
];

function matches(pathname: string, href: string, strategy?: "exact" | "prefix") {
  return strategy === "prefix"
    ? pathname === href || pathname.startsWith(`${href}/`)
    : pathname === href;
}

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
      {/* Mobile top bar with hamburger trigger. Same dark brand header as the
          marketing navbar -- it is the app's header at this breakpoint, and
          the two must not disagree about what a header looks like. The drawer
          below stays on --surface: it is a sidebar, not a header. */}
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-nav-border bg-nav-surface px-4 py-3 lg:hidden print:hidden">
        <Link href="/" className="flex items-center gap-2.5 rounded-chip focus-visible:outline-sand-300">
          <Wordmark tone="inverse" className="h-7" />
        </Link>
        <Button
          variant="ghost-inverse"
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

              const href = item.href;
              const inSection =
                matches(pathname, href, item.matchStrategy) ||
                (item.alsoActiveFor?.some((p) => pathname.startsWith(p)) ??
                  false);
              // A parent with children is highlighted only for its own page,
              // not for a child's -- otherwise both rows light up at once and
              // neither tells you where you are. `inSection` still governs
              // whether the child rows are revealed.
              const isActive = item.children ? pathname === href : inSection;

              return (
                <div key={item.label}>
                  <Link
                    href={href}
                    onClick={() => setIsOpen(false)}
                    aria-current={isActive ? "page" : undefined}
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
                  </Link>

                  {item.children && inSection && (
                    // Rendered only inside the active section: a permanently
                    // expanded tree would put every leaf back at the top level,
                    // which is the flatness this restructure removes. The rail
                    // on the left is what carries the "belongs to the item
                    // above" relationship visually.
                    <div className="mt-1 ml-6 space-y-1 border-l border-border pl-3">
                      {item.children.map((child) => {
                        const childActive = matches(
                          pathname,
                          child.href,
                          child.matchStrategy,
                        );
                        return (
                          <Link
                            key={child.href}
                            href={child.href}
                            onClick={() => setIsOpen(false)}
                            aria-current={childActive ? "page" : undefined}
                            className={cn(
                              "block rounded-full px-3 py-2 text-sm transition-colors",
                              childActive
                                ? "bg-brand-subtle font-semibold text-brand-fg"
                                : "text-fg-muted hover:bg-canvas-subtle hover:text-fg",
                            )}
                          >
                            {child.label}
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>
        </div>

        {/* Bottom Pro Callout & User Menu */}
        <div className="space-y-4">
          {!identityLoading && user && !isProfileComplete(user.profile) && (
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

          {/* The plan badge said "Free plan" to everyone, including paying
              subscribers, on every authenticated page -- and then offered
              them the chance to buy what they already had. It is bound to the
              real tier now (GOA-039).

              Nothing renders while identity is in flight: guessing Free would
              flash a paywall at a subscriber on every page load, which is the
              same reasoning as the exam landing page's isFreeTier. */}
          {!identityLoading && user && (
            <div className="space-y-3 rounded-panel border border-brand-border bg-brand-subtle p-4">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-brand-fg">
                <Icon icon={Sparkles} size="xs" />
                <span>
                  {user.subscriptionTier === "paid" ? "Dalil Pro" : "Free plan"}
                </span>
              </div>

              {user.subscriptionTier === "paid" ? (
                <>
                  <div>
                    <h4 className="text-sm leading-tight font-bold text-fg">
                      Every feature unlocked
                    </h4>
                    <p className="mt-1 text-[11px] leading-normal text-fg-muted">
                      Exams, AI scoring and CV review are all yours.
                    </p>
                  </div>
                  <Button size="sm" variant="outline" asChild>
                    <Link href="/profile">Manage subscription</Link>
                  </Button>
                </>
              ) : (
                <>
                  <div>
                    <h4 className="text-sm leading-tight font-bold text-fg">
                      Unlock Dalil Pro
                    </h4>
                    <p className="mt-1 text-[11px] leading-normal text-fg-muted">
                      Unlimited AI, CV review, IELTS scoring.
                    </p>
                  </div>
                  {/* Was an inert <Button> with no handler -- the one place in
                      the app that advertises the paid tier did nothing when
                      clicked. It now lands on /pricing (GOA-039), which knows
                      the caller's tier, rather than an anchor on the public
                      marketing page. */}
                  <Button size="sm" trailingIcon={ArrowRight} asChild>
                    <Link href={DEFAULT_UPGRADE_URL}>Upgrade</Link>
                  </Button>
                </>
              )}
            </div>
          )}

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
  const [open, setOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
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
    if (loggingOut) return;
    // The menu deliberately stays open: this is a network round trip, and
    // closing it first would leave the user with no indication that anything
    // is happening between the click and the redirect.
    setLoggingOut(true);
    try {
      await authApi.logout();
    } catch {
      // Best-effort: even if the network call fails, the client still treats
      // the session as ended rather than stranding the user on a dead menu.
    } finally {
      // A hard navigation, not router.push(). Three things have to observe the
      // cleared cookie for a logout to actually look like one, and a
      // client-side push guarantees none of them: middleware.ts decides
      // /login vs /chat from request cookies, the App Router keeps a
      // client-side RSC cache of the authenticated pages already visited, and
      // this component's own useCurrentUser state would otherwise survive the
      // transition still holding the old identity. assign() discards all
      // three by reloading the document.
      window.location.assign("/login");
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
          {identityLoading ? "···" : user ? emailInitials(user.email) : "?"}
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
            disabled={loggingOut}
            aria-busy={loggingOut || undefined}
            className="flex w-full items-center gap-2 rounded-control px-3 py-2 text-left text-sm text-fg transition-colors hover:bg-canvas-subtle disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Icon icon={LogOut} size="sm" />
            {loggingOut ? "Signing out…" : "Log out"}
          </button>
        </div>
      )}
    </div>
  );
}
