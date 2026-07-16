import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const BILLING_SERVICE_URL = process.env.BILLING_SERVICE_URL ?? "http://localhost:8006";
const USE_LOCAL_AUTH = process.env.NEXT_PUBLIC_USE_LOCAL_AUTH !== "false";

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

function forwardHeaders(request: NextRequest, hasBody: boolean, directBilling: boolean) {
  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  const contentType = request.headers.get("content-type");
  const token = authorization?.replace(/^Bearer\s+/i, "") ?? null;
  const claims = decodeJwtPayload(token);

  if (hasBody) headers.set("Content-Type", contentType ?? "application/json");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);

  if (directBilling) {
    headers.set("x-user-id", String(claims.sub ?? claims.user_id ?? "local-user"));
    headers.set("x-account-id", String(claims.account_id ?? claims.accountId ?? "dev-account"));
    headers.set("x-role", String(claims.role ?? "Owner"));
    if (claims.email) headers.set("x-user-email", String(claims.email));
  }

  return headers;
}

async function proxyBilling(request: NextRequest, pathParts: string[] = []) {
  const authorization = request.headers.get("authorization");
  const directBilling = USE_LOCAL_AUTH || authorization?.endsWith(".mock-signature") || !API_BASE_URL;
  const baseUrl = directBilling ? BILLING_SERVICE_URL : API_BASE_URL;
  const pathPrefix = directBilling ? "" : "/billing";

  if (!baseUrl) {
    return Response.json({ error: "Gateway API URL is not configured." }, { status: 500 });
  }

  const upstreamUrl = new URL(`${pathPrefix}/${pathParts.join("/")}`, baseUrl);
  request.nextUrl.searchParams.forEach((value, key) => upstreamUrl.searchParams.set(key, value));

  const method = request.method.toUpperCase();
  const hasBody = !["GET", "HEAD"].includes(method);

  try {
    const upstream = await fetch(upstreamUrl, {
      method,
      headers: forwardHeaders(request, hasBody, directBilling),
      body: hasBody ? await request.text() : undefined,
      cache: "no-store"
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" }
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Unable to reach the billing gateway." },
      { status: 502 }
    );
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyBilling(request, path);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyBilling(request, path);
}

export async function PUT(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyBilling(request, path);
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyBilling(request, path);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyBilling(request, path);
}
