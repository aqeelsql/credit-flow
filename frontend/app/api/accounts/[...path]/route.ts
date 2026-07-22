import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const ACCOUNT_SERVICE_URL = process.env.USER_TENANT_SERVICE_URL ?? process.env.ACCOUNT_SERVICE_URL ?? "http://localhost:8002";

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

function forwardHeaders(request: NextRequest, hasBody: boolean, directAccountService: boolean) {
  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  const contentType = request.headers.get("content-type");
  const token = authorization?.replace(/^Bearer\s+/i, "") ?? null;
  const claims = decodeJwtPayload(token);

  if (hasBody) headers.set("Content-Type", contentType ?? "application/json");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);

  if (directAccountService) {
    headers.set("x-user-id", String(claims.sub ?? claims.user_id ?? "local-user"));
    headers.set("x-account-id", String(claims.account_id ?? claims.accountId ?? ""));
    headers.set("x-role", String(claims.role ?? "Member"));
    if (claims.email) headers.set("x-user-email", String(claims.email));
  }

  return headers;
}

async function proxyAccounts(request: NextRequest, pathParts: string[] = []) {
  const directAccountService = !API_BASE_URL;
  const baseUrl = directAccountService ? ACCOUNT_SERVICE_URL : API_BASE_URL;
  const pathPrefix = directAccountService ? "" : "/accounts";
  const upstreamUrl = new URL(`${pathPrefix}/${pathParts.join("/")}`, baseUrl);
  request.nextUrl.searchParams.forEach((value, key) => upstreamUrl.searchParams.set(key, value));
  const method = request.method.toUpperCase();
  const hasBody = !["GET", "HEAD"].includes(method);
  try {
    const upstream = await fetch(upstreamUrl, {
      method,
      headers: forwardHeaders(request, hasBody, directAccountService),
      body: hasBody ? await request.text() : undefined,
      cache: "no-store"
    });
    const text = await upstream.text();
    return new Response(text, { status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to reach the Account service." }, { status: 502 });
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyAccounts(request, path);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyAccounts(request, path);
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyAccounts(request, path);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  return proxyAccounts(request, path);
}
