import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function forwardHeaders(request: NextRequest) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);
  return headers;
}

export async function GET(request: NextRequest) {
  if (!API_BASE_URL) {
    return Response.json({ error: "Gateway API URL is not configured." }, { status: 500 });
  }

  const upstreamUrl = new URL("/content/drafts", API_BASE_URL);
  const limit = request.nextUrl.searchParams.get("limit");
  if (limit) upstreamUrl.searchParams.set("limit", limit);

  try {
    const upstream = await fetch(upstreamUrl, {
      headers: forwardHeaders(request),
      cache: "no-store"
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" }
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Unable to reach the content gateway." },
      { status: 502 }
    );
  }
}

export async function POST(request: NextRequest) {
  if (!API_BASE_URL) {
    return Response.json({ error: "Gateway API URL is not configured." }, { status: 500 });
  }

  try {
    const upstream = await fetch(`${API_BASE_URL}/content/drafts`, {
      method: "POST",
      headers: forwardHeaders(request),
      body: await request.text(),
      cache: "no-store"
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" }
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Unable to reach the content gateway." },
      { status: 502 }
    );
  }
}
