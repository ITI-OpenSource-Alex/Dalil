import Link from "next/link";
import { Container } from "./section";
import { Wordmark } from "./wordmark";

/* ------------------------------------------------------------------ *
 * Sits one shade below the CTA (forest-950 against forest-900), so the
 * two dark sections read as depth rather than as one undifferentiated
 * block.
 *
 * Every link here resolves to something real. The previous footer carried
 * five href="#" placeholders -- About, Contact, Privacy Policy, Terms of
 * Service -- and dead links in a footer are a direct trust cost on the one
 * page whose job is trust. A Legal column is deliberately absent rather
 * than fake: those pages need to exist before they can be linked, and
 * writing them is not a frontend task.
 * ------------------------------------------------------------------ */

const COLUMNS = [
  {
    heading: "Product",
    links: [
      { label: "How it works", href: "#how-it-works" },
      { label: "Features", href: "#features" },
      { label: "Pricing", href: "#pricing" },
      { label: "FAQ", href: "#faq" },
    ],
  },
  {
    heading: "Get started",
    links: [
      { label: "Create an account", href: "/register" },
      { label: "Sign in", href: "/login" },
    ],
  },
  {
    heading: "Contact",
    links: [{ label: "hello@goa.app", href: "mailto:hello@goa.app" }],
  },
];

export function Footer() {
  return (
    <footer className="bg-forest-950">
      <h2 className="sr-only">Site footer</h2>

      <Container className="py-16 lg:py-20">
        <div className="grid gap-12 md:grid-cols-12">
          <div className="md:col-span-5">
            {/* See the note in navbar.tsx on why there is no aria-label. */}
            <Link href="/" className="inline-block rounded-chip">
              <Wordmark tone="inverse" />
              <span className="sr-only">home</span>
            </Link>

            <p className="mt-4 max-w-xs text-sm leading-6 text-forest-200/80">
              The AI study abroad platform — matching, application checklists
              and IELTS preparation in one assistant.
            </p>
          </div>

          <div className="grid gap-10 sm:grid-cols-3 md:col-span-7">
            {COLUMNS.map((column) => (
              <div key={column.heading}>
                <h3 className="text-sm font-semibold text-fg-inverse">
                  {column.heading}
                </h3>
                <ul className="mt-4 flex flex-col gap-3">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      <Link
                        href={link.href}
                        className="rounded-chip text-sm text-forest-200/70 transition-colors duration-120 ease-out hover:text-fg-inverse focus-visible:outline-sand-300"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-3 border-t border-forest-800 pt-8 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-forest-200/60">
            © {new Date().getFullYear()} Dalil. All rights reserved.
          </p>
          <p className="text-sm text-forest-200/60">
            Not affiliated with the IELTS test owners.
          </p>
        </div>
      </Container>
    </footer>
  );
}
