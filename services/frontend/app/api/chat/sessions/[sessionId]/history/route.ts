import { NextRequest, NextResponse } from "next/server";

// Server-side only — see app/api/chat/route.ts for why this isn't NEXT_PUBLIC_*.
const ORCHESTRATION_URL =
  process.env.ORCHESTRATION_SERVICE_URL ?? "http://localhost:8083";

export const dynamic = "force-dynamic";

// Proxies GET /api/chat/sessions/:sessionId/history (called by
// components/chat/chat-shell.tsx on mount) to Orchestration's
// GET /sessions/:sessionId/history.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${ORCHESTRATION_URL}/sessions/${encodeURIComponent(sessionId)}/history`,
    );
  } catch {
    return NextResponse.json(
      { error: "Orchestration service unavailable" },
      { status: 502 },
    );
  }

  const data = await upstream.text();
  return new NextResponse(data, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
