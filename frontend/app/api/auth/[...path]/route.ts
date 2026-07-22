import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const AUTH_SERVICE_URL = process.env.AUTH_SERVICE_URL ?? "http://localhost:8001";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function forwardHeaders(request: NextRequest, hasBody: boolean) {
  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  const contentType = request.headers.get("content-type");
  const forwardedFor = request.headers.get("x-forwarded-for");

  if (hasBody) headers.set("Content-Type", contentType ?? "application/json");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  return headers;
}

async function proxyAuth(request: NextRequest, pathParts: string[] = []) {
  const baseUrl = API_BASE_URL || AUTH_SERVICE_URL;
  const pathPrefix = API_BASE_URL ? "/auth" : "";
  const upstreamUrl = new URL(`${pathPrefix}/${pathParts.join("/")}`, baseUrl);
  request.nextUrl.searchParams.forEach((value, key) => upstreamUrl.searchParams.set(key, value));

  const method = request.method.toUpperCase();
  const hasBody = !["GET", "HEAD"].includes(method);

  try {
    const upstream = await fetch(upstreamUrl, {
      method,
      headers: forwardHeaders(request, hasBody),
      body: hasBody ? await request.text() : undefined,
      cache: "no-store"
    });
    const text = await upstream.text();
    const response = new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" }
    });
    const setCookie = upstream.headers.get("set-cookie");
    if (setCookie) response.headers.set("set-cookie", setCookie);
    return response;
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to reach the Auth service." }, { status: 502 });
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyAuth(request, path);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyAuth(request, path);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyAuth(request, path);
}
