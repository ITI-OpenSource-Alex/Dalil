import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Route protection.
 *
 * This is a *navigation* guard, not an authorisation boundary. It checks that
 * an access_token cookie is present — it does not verify the signature, and it
 * cannot: the JWT secret belongs to the Gateway and must not be shipped to the
 * Next.js runtime to satisfy a redirect. Every protected route's data still
 * comes from the Gateway, which validates the token properly on every request
 * (middleware.JWT), so a forged cookie buys an empty shell and 401s, not data.
 *
 * What the guard is for is the thing that was actually broken: a signed-out
 * visitor could open /opportunities and get the full application chrome with
 * "Not signed in" in the corner and empty panels where their data should be.
 * That reads as a broken product, and it leaks the shape of the app to anyone
 * who types a URL.
 */
const PROTECTED_PREFIXES = [
  "/dashboard",
  "/chat",
  "/profile",
  "/opportunities",
  // Two separate routes, not one prefix: /checklist/:programId is the detail
  // page and /checklists is the index. Matching "/checklist" alone would leave
  // the index open, since "/checklists" is neither equal to it nor under it.
  "/checklist",
  "/checklists",
  "/exam",
  "/onboarding",
  "/speaking/history",
  "/practice",
  "/cv-review",
];

/** Signed-in users have no business on these; send them into the app instead. */
const AUTH_ROUTES = ["/login", "/register"];

/** Where a signed-in user lands when they ask for /login with no destination. */
const DEFAULT_SIGNED_IN_DESTINATION = "/chat";

function isProtected(pathname: string): boolean {
  // /speaking/share/:token is deliberately absent: a share link is meant to be
  // opened by someone with no account. /speaking itself (the live practice
  // page) is protected by exact match so the share prefix stays public.
  if (pathname === "/speaking") return true;
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Only same-origin, path-absolute destinations survive.
 *
 * `redirectUrl` arrives from the query string, so it is attacker-controlled: a
 * value like `//evil.example` or `https://evil.example` is a path to the
 * browser's URL parser but an off-site redirect in practice, and an open
 * redirect on a login page is a credible phishing primitive — the victim really
 * did start on your domain.
 */
function safeRedirectTarget(raw: string | null): string | null {
  if (!raw) return null;
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//") || raw.startsWith("/\\")) return null;
  return raw;
}

export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token");
  const { pathname, search } = request.nextUrl;

  if (isProtected(pathname) && !token) {
    const login = new URL("/login", request.url);
    // Preserve the query string too: /checklist/abc?tab=documents should come
    // back whole, not stripped to /checklist/abc.
    login.searchParams.set("redirectUrl", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }

  if (AUTH_ROUTES.some((route) => pathname.startsWith(route)) && token) {
    const requested = safeRedirectTarget(
      request.nextUrl.searchParams.get("redirectUrl"),
    );
    return NextResponse.redirect(
      new URL(requested ?? DEFAULT_SIGNED_IN_DESTINATION, request.url),
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/chat/:path*",
    "/profile/:path*",
    "/opportunities/:path*",
    "/speaking",
    "/speaking/history/:path*",
    "/checklist/:path*",
    "/checklists/:path*",
    "/exam/:path*",
    "/onboarding/:path*",
    "/practice/:path*",
    "/cv-review/:path*",
    "/login",
    "/register",
  ],
};
