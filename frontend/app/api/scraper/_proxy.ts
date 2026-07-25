import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const SCRAPER_SERVICE_URL =
  process.env.SCRAPER_SERVICE_URL ??
  process.env.GATEWAY_SCRAPER_SERVICE_URL ??
  process.env.SCRAPER_SERVICE_BASE_URL ??
  "http://localhost:8012";

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    return JSON.parse(Buffer.from(padded, "base64").toString("utf8")) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function stringClaim(payload: Record<string, unknown> | null, keys: string[]) {
  for (const key of keys) {
    const value = payload?.[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

export function forwardScraperHeaders(request: NextRequest) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);

  const bearer = authorization?.match(/^Bearer\s+(.+)$/i)?.[1];
  const payload = bearer ? decodeJwtPayload(bearer) : null;
  const userId = stringClaim(payload, ["sub", "user_id"]);
  const accountId = stringClaim(payload, ["account_id"]);
  const role = stringClaim(payload, ["role"]);
  const jti = stringClaim(payload, ["jti"]);
  const email = stringClaim(payload, ["email"]);

  if (userId) headers.set("x-user-id", userId);
  if (accountId) headers.set("x-account-id", accountId);
  if (role) headers.set("x-role", role);
  if (jti) headers.set("x-jti", jti);
  if (email) headers.set("x-user-email", email);
  return headers;
}

async function forward(url: string, init: RequestInit, headers: Headers, body: BodyInit | null | undefined) {
  const upstream = await fetch(url, { ...init, headers, body, cache: "no-store" });
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" }
  });
}

function shouldFallbackToDirect(response: Response) {
  return response.status === 404 || response.status === 502 || response.status === 503 || response.status === 504;
}

export async function proxyScraperRequest(request: NextRequest, path: string, init: RequestInit = {}) {
  const headers = forwardScraperHeaders(request);
  const body = init.body;
  const gatewayUrl = API_BASE_URL ? `${API_BASE_URL}/scraper${path}` : "";
  const directUrl = `${SCRAPER_SERVICE_URL}/scraper${path}`;

  if (gatewayUrl) {
    try {
      const gateway = await fetch(gatewayUrl, { ...init, headers, body, cache: "no-store" });
      if (!shouldFallbackToDirect(gateway)) {
        const text = await gateway.text();
        return new Response(text, {
          status: gateway.status,
          headers: { "Content-Type": gateway.headers.get("content-type") ?? "application/json" }
        });
      }
    } catch {
      // Fall through to direct scraper service below.
    }
  }

  try {
    return await forward(directUrl, init, headers, body);
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to reach the scraper service." }, { status: 502 });
  }
}