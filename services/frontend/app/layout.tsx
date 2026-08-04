import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
