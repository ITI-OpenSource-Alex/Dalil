"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChevronDown, LayoutGrid, LogOut, Menu, User as UserIcon, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { authApi } from "@/lib/api";
import { getMyProfile } from "@/lib/profile-api";
import { emailInitials } from "@/lib/user-display";
import { Button, Icon } from "@/components/ui";
import { Wordmark } from "./wordmark";

const LINKS = [
  { label: "How it works", href: "#how-it-works" },
  { label: "Features", href: "#features" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
];

/** Where the signed-in CTA goes. Matching ProtectedShell's own landing route. */
const APP_HOME = "/dashboard";

/**
 * The previous navbar's mobile button had no onClick, no aria-label and no
 * aria-expanded -- it was an inert control, and the landing page had no
 * mobile navigation at all. This is the smallest client island that fixes
 * that plus the scroll state; every other section on the page stays a
 * Server Component.
 */
export function Navbar({ signedIn = false }: { signedIn?: boolean }) {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const accountRef = useRef<HTMLDivElement>(null);

  // Only for the email on the account button, and only when the server already
  // told us there is a session. An anonymous visitor to the landing page makes
  // no API call at all — the marketing page should not issue a request that is
  // guaranteed to 401.
  useEffect(() => {
    if (!signedIn) return;
    let cancelled = false;
    getMyProfile()
      .then((me) => {
        if (!cancelled) setEmail(me.email);
      })
      .catch(() => {
        // A stale or rejected cookie leaves the CTA as "Open app"; the
        // Gateway is what decides whether that click succeeds, and the
        // middleware redirect handles the signed-out case from there.
      });
    return () => {
      cancelled = true;
    };
  }, [signedIn]);

  // Click-outside and Escape for the account menu, matching the sidebar's.
  useEffect(() => {
    if (!accountOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) {
        setAccountOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAccountOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [accountOpen]);

  async function handleSignOut() {
    try {
      await authApi.logout();
    } catch {
      // Same reasoning as the sidebar's menu: a failed logout call must still
      // end the session locally rather than stranding the user on a dead menu.
    } finally {
      // Hard navigation, not router.push: middleware.ts reads the cleared
      // cookie from the request, and this page's own server-rendered
      // `signedIn` prop would otherwise survive the transition.
      window.location.assign("/");
    }
  }

  // The bar is now a solid dark brand surface at every scroll position, so
  // this drives elevation only: flat while the page is at the top, lifted off
  // the content once it moves. Passive listener: it must never block
  // scrolling.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Escape closes, and focus returns to the trigger rather than being lost
  // to the top of the document.
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    // Prevent the page scrolling behind the open panel.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Move focus into the panel so the next Tab lands on a menu link.
    panelRef.current?.focus();

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previous;
    };
  }, [open]);

  return (
    <header
      className={cn(
        "sticky top-0 z-1100 border-b bg-nav-surface transition-[border-color,box-shadow] duration-200 ease-out",
        scrolled || open
          ? "border-nav-border shadow-e3"
          : "border-transparent shadow-none",
      )}
    >
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-6 px-6 lg:px-8">
        {/* No aria-label: overriding the name of a link whose visible text is
            the wordmark trips axe's label-content-name-mismatch, because the
            override ("Dalil — home") does not contain the visible text. Letting
            the name come from content, plus an sr-only suffix, says the same
            thing without the conflict. */}
        <Link href="/" className="rounded-chip focus-visible:outline-sand-300">
          {/* Inverse variant: the artwork ships in forest ink, which would be
              all but invisible on the forest-900 bar. */}
          <Wordmark tone="inverse" className="h-7 sm:h-8" />
          <span className="sr-only">home</span>
        </Link>

        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex items-center gap-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="rounded-control px-3 py-2 text-sm font-medium text-nav-fg-muted transition-colors duration-120 ease-out hover:bg-nav-hover hover:text-nav-fg focus-visible:outline-sand-300"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="hidden items-center gap-2 lg:flex">
          {signedIn ? (
            <>
              <Button asChild variant="inverse" size="sm" leadingIcon={LayoutGrid}>
                <Link href={APP_HOME}>Open app</Link>
              </Button>

              <div ref={accountRef} className="relative">
                <button
                  type="button"
                  onClick={() => setAccountOpen((value) => !value)}
                  aria-expanded={accountOpen}
                  aria-haspopup="menu"
                  className="flex items-center gap-2 rounded-control px-1.5 py-1.5 transition-colors duration-120 ease-out hover:bg-nav-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sand-300"
                >
                  <span
                    aria-hidden="true"
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-forest-700 text-xs font-bold text-nav-fg"
                  >
                    {email ? emailInitials(email) : "···"}
                  </span>
                  {/* The button's accessible name has to say who this is even
                      before the email lands, or it reads as "menu" to a screen
                      reader while showing an avatar to everyone else. */}
                  <span className="sr-only">
                    {email ? `Account menu for ${email}` : "Account menu"}
                  </span>
                  <Icon
                    icon={ChevronDown}
                    size="xs"
                    className={cn(
                      "text-nav-fg-muted transition-transform duration-120",
                      accountOpen && "rotate-180",
                    )}
                  />
                </button>

                {accountOpen && (
                  <div
                    role="menu"
                    aria-label="Account"
                    className="absolute right-0 top-full z-10 mt-2 w-60 rounded-panel border border-border bg-surface-raised p-1.5 shadow-e2"
                  >
                    {email && (
                      <p className="truncate px-3 py-2 text-xs font-semibold text-fg-subtle">
                        {email}
                      </p>
                    )}
                    <Link
                      role="menuitem"
                      href="/opportunities"
                      onClick={() => setAccountOpen(false)}
                      className="flex items-center gap-2 rounded-control px-3 py-2 text-sm text-fg transition-colors hover:bg-canvas-subtle"
                    >
                      <Icon icon={LayoutGrid} size="sm" />
                      Opportunities
                    </Link>
                    <Link
                      role="menuitem"
                      href="/profile"
                      onClick={() => setAccountOpen(false)}
                      className="flex items-center gap-2 rounded-control px-3 py-2 text-sm text-fg transition-colors hover:bg-canvas-subtle"
                    >
                      <Icon icon={UserIcon} size="sm" />
                      Profile
                    </Link>
                    <button
                      role="menuitem"
                      type="button"
                      onClick={() => void handleSignOut()}
                      className="flex w-full items-center gap-2 rounded-control px-3 py-2 text-left text-sm text-fg transition-colors hover:bg-canvas-subtle"
                    >
                      <Icon icon={LogOut} size="sm" />
                      Sign out
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <Button asChild variant="ghost-inverse" size="sm">
                <Link href="/login">Sign in</Link>
              </Button>
              <Button asChild variant="inverse" size="sm">
                <Link href="/register">Get started</Link>
              </Button>
            </>
          )}
        </div>

        <button
          ref={triggerRef}
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          className="inline-flex h-11 w-11 items-center justify-center rounded-control text-nav-fg transition-colors duration-120 ease-out hover:bg-nav-hover focus-visible:outline-sand-300 lg:hidden"
        >
          <Icon icon={open ? X : Menu} size="md" />
        </button>
      </div>

      {/* Mobile panel. Rendered only when open so its links never sit in the
          tab order of the desktop layout. */}
      {open && (
        <div
          id="mobile-nav"
          ref={panelRef}
          tabIndex={-1}
          className="border-t border-nav-border bg-nav-surface lg:hidden focus-visible:outline-none"
        >
          <nav aria-label="Mobile" className="px-6 py-4">
            <ul className="flex flex-col">
              {LINKS.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    onClick={() => setOpen(false)}
                    className="block rounded-control px-3 py-3 text-base font-medium text-nav-fg transition-colors duration-120 ease-out hover:bg-nav-hover focus-visible:outline-sand-300"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>

            <div className="mt-4 flex flex-col gap-2 border-t border-nav-border pt-4">
              {signedIn ? (
                <>
                  {email && (
                    <p className="truncate px-3 pb-1 text-xs font-semibold text-nav-fg-muted">
                      Signed in as {email}
                    </p>
                  )}
                  <Button asChild variant="inverse" fullWidth leadingIcon={LayoutGrid}>
                    <Link href={APP_HOME} onClick={() => setOpen(false)}>
                      Open app
                    </Link>
                  </Button>
                  <Button asChild variant="ghost-inverse" fullWidth>
                    <Link href="/profile" onClick={() => setOpen(false)}>
                      Profile
                    </Link>
                  </Button>
                  <Button
                    variant="ghost-inverse"
                    fullWidth
                    leadingIcon={LogOut}
                    onClick={() => {
                      setOpen(false);
                      void handleSignOut();
                    }}
                  >
                    Sign out
                  </Button>
                </>
              ) : (
                <>
                  <Button asChild variant="ghost-inverse" fullWidth>
                    <Link href="/login" onClick={() => setOpen(false)}>
                      Sign in
                    </Link>
                  </Button>
                  <Button asChild variant="inverse" fullWidth>
                    <Link href="/register" onClick={() => setOpen(false)}>
                      Get started free
                    </Link>
                  </Button>
                </>
              )}
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
