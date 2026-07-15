import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const LINKEDIN_SERVICE_URL = process.env.LINKEDIN_SERVICE_URL ?? "http://localhost:8005";

function forwardHeaders(request: NextRequest) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);

  // Local-dev fallback when the browser is talking directly to the service without the API Gateway.
  headers.set("x-user-id", request.headers.get("x-user-id") ?? "dev-user");
  headers.set("x-account-id", request.headers.get("x-account-id") ?? "dev-account");
  headers.set("x-role", request.headers.get("x-role") ?? "Owner");
  return headers;
}

async function proxy(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const params = await context.params;
  const path = `/${(params.path ?? []).join("/")}`;
  const headers = forwardHeaders(request);
  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.text();
  const gatewayUrl = API_BASE_URL ? `${API_BASE_URL}/linkedin${path}` : "";
  const directUrl = `${LINKEDIN_SERVICE_URL}/linkedin${path}`;

  try {
    const upstream = gatewayUrl
      ? await fetch(gatewayUrl, { method: request.method, headers, body, cache: "no-store" })
      : await fetch(directUrl, { method: request.method, headers, body, cache: "no-store" });
    if (upstream.status !== 404 || !gatewayUrl) {
      const text = await upstream.text();
      return new Response(text, { status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" } });
    }
    const direct = await fetch(directUrl, { method: request.method, headers, body, cache: "no-store" });
    const directText = await direct.text();
    return new Response(directText, { status: direct.status, headers: { "Content-Type": direct.headers.get("content-type") ?? "application/json" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to reach LinkedIn service." }, { status: 502 });
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return proxy(request, context);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return proxy(request, context);
}

