import { NextRequest } from "next/server";

// Server-side only — never exposed to the browser. Route Handlers run on the
// Next.js server, so this call to Orchestration is server-to-server and never
// needs CORS, unlike the NEXT_PUBLIC_*_API_URL clients in lib/*-api.ts that
// fetch other services directly from the browser.
const ORCHESTRATION_URL =
  process.env.ORCHESTRATION_SERVICE_URL ?? "http://localhost:8083";

export const dynamic = "force-dynamic";

// Proxies POST /api/chat (same-origin, called by components/chat/chat-shell.tsx)
// to Orchestration's POST /chat, relaying the upstream SSE stream straight
// through without buffering so tokens still arrive incrementally.
export async function POST(request: NextRequest) {
  const body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${ORCHESTRATION_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch {
    return new Response(
      JSON.stringify({ error: "Orchestration service unavailable" }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") ?? "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
