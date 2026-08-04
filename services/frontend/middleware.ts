import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token");

  const pathname = request.nextUrl.pathname;

  const isProtectedRoute =
    pathname.startsWith("/chat") ||
    pathname.startsWith("/profile") ||
    pathname.startsWith("/speaking/history") ||
    pathname.startsWith("/checklist");

  const isAuthRoute = pathname.startsWith("/login") || pathname.startsWith("/register");

  // if (isProtectedRoute && !token) {
  //   return NextResponse.redirect(new URL("/login", request.url));
  // }

  if (isAuthRoute && token) {
    return NextResponse.redirect(new URL("/chat", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/chat/:path*",
    "/profile/:path*",
    "/speaking/history/:path*",
    "/checklist/:path*",
    "/login",
    "/register",
  ],
};
