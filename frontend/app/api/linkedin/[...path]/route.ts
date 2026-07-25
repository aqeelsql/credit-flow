import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const LINKEDIN_SERVICE_URL = process.env.LINKEDIN_SERVICE_URL ?? "http://localhost:8005";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function decodeJwtPayload(token: string | null): Record<string, unknown> {
  if (!token || !token.includes(".")) return {};
  try {
    const [, payload] = token.split(".");
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(Buffer.from(normalized, "base64").toString("utf8")) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function forwardHeaders(request: NextRequest, hasBody: boolean, directLinkedIn: boolean) {
  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  const contentType = request.headers.get("content-type");
  const token = authorization?.replace(/^Bearer\s+/i, "") ?? null;
  const claims = decodeJwtPayload(token);

  if (hasBody) headers.set("Content-Type", contentType ?? "application/json");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);

  if (directLinkedIn) {
    headers.set("x-user-id", String(claims.sub ?? claims.user_id ?? "local-user"));
    headers.set("x-account-id", String(claims.account_id ?? claims.accountId ?? ""));
    headers.set("x-role", String(claims.role ?? "Owner"));
    if (claims.email) headers.set("x-user-email", String(claims.email));
  }
  return headers;
}

async function proxy(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const params = await context.params;
  const path = `/${(params.path ?? []).join("/")}`;
  const directLinkedIn = !API_BASE_URL;
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const headers = forwardHeaders(request, hasBody, directLinkedIn);
  const body = hasBody ? await request.text() : undefined;
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

