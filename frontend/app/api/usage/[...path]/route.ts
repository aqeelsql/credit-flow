import { NextRequest } from "next/server";

const API_BASE_URL = process.env.API_GATEWAY_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const USAGE_SERVICE_URL = process.env.USAGE_SERVICE_URL ?? "http://localhost:8009";

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

async function proxy(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const params = await context.params;
  const path = `/${(params.path ?? []).join("/")}`;
  const query = request.nextUrl.search;
  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.text();
  const gatewayUrl = API_BASE_URL ? `${API_BASE_URL}/usage${path}${query}` : "";
  const directUrl = `${USAGE_SERVICE_URL}${path}${query}`;
  try {
    const upstream = gatewayUrl
      ? await fetch(gatewayUrl, { method: request.method, headers: forwardHeaders(request), body, cache: "no-store" })
      : await fetch(directUrl, { method: request.method, headers: forwardHeaders(request), body, cache: "no-store" });
    if (upstream.status !== 404 || !gatewayUrl) {
      const text = await upstream.text();
      return new Response(text, { status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" } });
    }
    const direct = await fetch(directUrl, { method: request.method, headers: forwardHeaders(request), body, cache: "no-store" });
    const text = await direct.text();
    return new Response(text, { status: direct.status, headers: { "Content-Type": direct.headers.get("content-type") ?? "application/json" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to reach Usage Service." }, { status: 502 });
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return proxy(request, context);
}
