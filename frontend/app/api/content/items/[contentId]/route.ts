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

async function proxy(request: NextRequest, contentId: string, method: "GET" | "PATCH" | "DELETE") {
  if (!API_BASE_URL) {
    return Response.json({ error: "Gateway API URL is not configured." }, { status: 500 });
  }

  try {
    const upstream = await fetch(`${API_BASE_URL}/content/items/${contentId}`, {
      method,
      headers: forwardHeaders(request),
      body: method === "PATCH" ? await request.text() : undefined,
      cache: "no-store"
    });
    if (upstream.status === 204) {
      return new Response(null, { status: 204 });
    }
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

export async function GET(request: NextRequest, { params }: { params: Promise<{ contentId: string }> }) {
  const { contentId } = await params;
  return proxy(request, contentId, "GET");
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ contentId: string }> }) {
  const { contentId } = await params;
  return proxy(request, contentId, "PATCH");
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ contentId: string }> }) {
  const { contentId } = await params;
  return proxy(request, contentId, "DELETE");
}
