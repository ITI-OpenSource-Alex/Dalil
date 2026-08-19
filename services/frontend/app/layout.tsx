import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  // Required for Next to resolve the relative openGraph/twitter image URLs
  // below into absolute ones -- without it, social crawlers get a
  // localhost-relative URL they can't fetch. NEXT_PUBLIC_APP_URL matches
  // this project's existing convention of falling back to the local dev
  // default when unset (see lib/api.ts's NEXT_PUBLIC_API_URL for the same
  // pattern).
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"),
  title: "Dalil - Global Opportunity Assistant",
  description: "AI-Powered Study Abroad & IELTS Companion",
  openGraph: {
    title: "Dalil - Global Opportunity Assistant",
    description: "AI-Powered Study Abroad & IELTS Companion",
    type: "website",
    images: [{ url: "/og-image.svg", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Dalil - Global Opportunity Assistant",
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
    <html lang="en" className="h-full antialiased">
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
