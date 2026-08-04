import type { Metadata } from "next";
import { Geist, Geist_Mono, Fraunces } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

// preload: false — Geist Mono is used only for the occasional code-style
// label (the design-system reference page, essentially). Preloading it put a
// third font on the critical path of every route, including the landing page,
// where no monospace text is rendered at all. It still loads on demand
// wherever font-mono is actually applied.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
  preload: false,
});

// Display face for page- and section-level headings. Applied deliberately at
// display sizes (via the Heading primitive and the marketing sections), not
// globally to every h1-h6 -- a serif on a 14px `<h2>` section label, of which
// this app has several, reads as a mistake rather than as a voice.
//
// Loaded as a variable font on the weight axis only. Fraunces' other axes
// (SOFT, WONK, opsz) stay at their defaults, which is the clean, high-end cut
// -- opting them in would make them variable too and inflate the file for no
// benefit here.
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  // Required for Next to resolve the relative openGraph/twitter image URLs
  // below into absolute ones -- without it, social crawlers get a
  // localhost-relative URL they can't fetch. NEXT_PUBLIC_APP_URL matches
  // this project's existing convention of falling back to the local dev
  // default when unset (see lib/api.ts's NEXT_PUBLIC_API_URL for the same
  // pattern).
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"),
  title: "GOA - Global Opportunity Assistant",
  description: "AI-Powered Study Abroad & IELTS Companion",
  openGraph: {
    title: "GOA - Global Opportunity Assistant",
    description: "AI-Powered Study Abroad & IELTS Companion",
    type: "website",
    images: [{ url: "/og-image.svg", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "GOA - Global Opportunity Assistant",
    description: "AI-Powered Study Abroad & IELTS Companion",
    images: ["/og-image.svg"],
  },
};


export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        {/* Lets keyboard and screen-reader users bypass the navbar/sidebar on
            every route. Visually hidden until focused. Pages provide the
            target by putting id="main-content" on their <main>. */}
        <a
          href="#main-content"
          className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:top-4 focus-visible:left-4 focus-visible:z-1400 focus-visible:rounded-control focus-visible:bg-brand focus-visible:px-4 focus-visible:py-2 focus-visible:text-sm focus-visible:font-semibold focus-visible:text-fg-on-brand"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
