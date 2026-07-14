import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (!API_BASE_URL) {
    return Response.json({ error: "Gateway API URL is not configured." }, { status: 500 });
  }

  const upstreamUrl = new URL("/content/generate/stream", API_BASE_URL);
  const accountId = request.nextUrl.searchParams.get("account_id");
  const prompt = request.nextUrl.searchParams.get("prompt");

  if (accountId) upstreamUrl.searchParams.set("account_id", accountId);
  if (prompt) upstreamUrl.searchParams.set("prompt", prompt);

  const headers = new Headers({ Accept: "text/event-stream" });
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);

  try {
    const upstream = await fetch(upstreamUrl, {
      headers,
      cache: "no-store"
    });

    if (!upstream.ok || !upstream.body) {
      const message = await upstream.text().catch(() => "");
      return Response.json(
        { error: message || `Generation request failed (${upstream.status}).` },
        { status: upstream.status }
      );
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "Content-Type": "text/event-stream; charset=utf-8",
        "X-Accel-Buffering": "no"
      }
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Unable to reach the generation gateway." },
      { status: 502 }
    );
  }
}
