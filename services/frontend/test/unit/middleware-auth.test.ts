import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";
import { safeRedirectTarget } from "@/components/auth/LoginForm";

function request(url: string, cookie?: string) {
  const req = new NextRequest(new URL(url, "http://localhost:3000"));
  if (cookie) req.cookies.set("access_token", cookie);
  return req;
}

describe("middleware route protection", () => {
  const PROTECTED = [
    "/opportunities",
    "/opportunities/anything",
    "/chat",
    "/profile",
    "/checklist/prog-1",
    "/checklists",
    "/exam",
    "/exam/shell?session=abc",
    "/onboarding",
    "/speaking",
    "/speaking/history",
    // Phase E (docs/IA-REDESIGN-PROPOSAL.md): the Dashboard and CV Review
    // pages. /practice was already added in Phase D but had never actually
    // been added to PROTECTED_PREFIXES until now -- a signed-out visitor
    // could open /practice/speaking and get the full app shell.
    "/dashboard",
    "/practice",
    "/practice/speaking",
    "/practice/writing/history",
    "/cv-review",
  ];

  it.each(PROTECTED)("redirects a signed-out visitor away from %s", (path) => {
    const response = middleware(request(path));
    const location = new URL(response.headers.get("location")!);

    expect(response.status).toBe(307);
    expect(location.pathname).toBe("/login");
    // The whole destination, query string included, so the round trip lands
    // the user back where they were actually going.
    expect(location.searchParams.get("redirectUrl")).toBe(path);
  });

  it.each(PROTECTED)("lets a signed-in visitor through to %s", (path) => {
    const response = middleware(request(path, "token"));
    expect(response.headers.get("location")).toBeNull();
  });

  it("leaves public routes alone in both states", () => {
    // A share link's recipient has no account by definition.
    for (const path of ["/", "/speaking/sessions/public/abc", "/forgot-password"]) {
      expect(middleware(request(path)).headers.get("location")).toBeNull();
    }
  });

  it("sends a signed-in visitor on /login into the app", () => {
    const response = middleware(request("/login", "token"));
    expect(new URL(response.headers.get("location")!).pathname).toBe("/dashboard");
  });

  it("honours redirectUrl when a signed-in visitor lands on /login", () => {
    const response = middleware(request("/login?redirectUrl=/opportunities", "token"));
    expect(new URL(response.headers.get("location")!).pathname).toBe("/opportunities");
  });

  it("refuses an off-site redirectUrl rather than following it", () => {
    const response = middleware(
      request("/login?redirectUrl=//evil.example/steal", "token"),
    );
    const location = new URL(response.headers.get("location")!);
    expect(location.hostname).toBe("localhost");
    expect(location.pathname).toBe("/dashboard");
  });
});

describe("safeRedirectTarget", () => {
  it("accepts same-origin paths", () => {
    expect(safeRedirectTarget("/opportunities")).toBe("/opportunities");
    expect(safeRedirectTarget("/checklist/a?tab=docs")).toBe("/checklist/a?tab=docs");
  });

  it("rejects anything that could leave the origin", () => {
    // Each of these is a redirect off-site despite looking path-like, which is
    // what makes an open redirect on a login page a usable phishing hop.
    for (const hostile of [
      "//evil.example",
      "/\\evil.example",
      "https://evil.example",
      "javascript:alert(1)",
      "",
      null,
    ]) {
      expect(safeRedirectTarget(hostile)).toBeNull();
    }
  });
});
