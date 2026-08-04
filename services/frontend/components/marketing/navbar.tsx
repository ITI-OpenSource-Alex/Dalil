"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button, Icon } from "@/components/ui";
import { Wordmark } from "./wordmark";

const LINKS = [
  { label: "How it works", href: "#how-it-works" },
  { label: "Features", href: "#features" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
];

/**
 * The previous navbar's mobile button had no onClick, no aria-label and no
 * aria-expanded -- it was an inert control, and the landing page had no
 * mobile navigation at all. This is the smallest client island that fixes
 * that plus the scroll state; every other section on the page stays a
 * Server Component.
 */
export function Navbar() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Transparent over the hero, solid once the page moves. Passive listener:
  // this must never block scrolling.
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
        "sticky top-0 z-1100 transition-[background-color,border-color,backdrop-filter] duration-200 ease-out",
        scrolled || open
          ? "border-b border-border bg-canvas/85 backdrop-blur-md"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-6 px-6 lg:px-8">
        {/* No aria-label: overriding the name of a link whose visible text is
            the wordmark trips axe's label-content-name-mismatch, because the
            override ("GOA — home") does not contain the visible text. Letting
            the name come from content, plus an sr-only suffix, says the same
            thing without the conflict. */}
        <Link href="/" className="rounded-chip">
          <Wordmark />
          <span className="sr-only">home</span>
        </Link>

        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex items-center gap-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="rounded-control px-3 py-2 text-sm font-medium text-fg-muted transition-colors duration-120 ease-out hover:bg-canvas-subtle hover:text-fg"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="hidden items-center gap-2 lg:flex">
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/register">Get started</Link>
          </Button>
        </div>

        <button
          ref={triggerRef}
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          className="inline-flex h-11 w-11 items-center justify-center rounded-control text-fg transition-colors duration-120 ease-out hover:bg-canvas-subtle lg:hidden"
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
          className="border-t border-border bg-canvas lg:hidden focus-visible:outline-none"
        >
          <nav aria-label="Mobile" className="px-6 py-4">
            <ul className="flex flex-col">
              {LINKS.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    onClick={() => setOpen(false)}
                    className="block rounded-control px-3 py-3 text-base font-medium text-fg transition-colors duration-120 ease-out hover:bg-canvas-subtle"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>

            <div className="mt-4 flex flex-col gap-2 border-t border-border pt-4">
              <Button asChild variant="secondary" fullWidth>
                <Link href="/login" onClick={() => setOpen(false)}>
                  Sign in
                </Link>
              </Button>
              <Button asChild fullWidth>
                <Link href="/register" onClick={() => setOpen(false)}>
                  Get started free
                </Link>
              </Button>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
