import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const SCRAPER_SERVICE_URL = process.env.SCRAPER_SERVICE_URL ?? "http://localhost:8012";

export function forwardScraperHeaders(request: NextRequest) {
  const headers = new Headers({ "Content-Type": "application/json" });
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);
  return headers;
}

export async function proxyScraperRequest(request: NextRequest, path: string, init: RequestInit = {}) {
  const headers = forwardScraperHeaders(request);
  const body = init.body;
  const gatewayUrl = API_BASE_URL ? `${API_BASE_URL}/scraper${path}` : "";
  const directUrl = `${SCRAPER_SERVICE_URL}/scraper${path}`;

  try {
    const upstream = gatewayUrl
      ? await fetch(gatewayUrl, { ...init, headers, body, cache: "no-store" })
      : await fetch(directUrl, { ...init, headers, body, cache: "no-store" });
    if (upstream.status !== 404 || !gatewayUrl) {
      const text = await upstream.text();
      return new Response(text, { status: upstream.status, headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" } });
    }

    const direct = await fetch(directUrl, { ...init, headers, body, cache: "no-store" });
    const directText = await direct.text();
    return new Response(directText, { status: direct.status, headers: { "Content-Type": direct.headers.get("content-type") ?? "application/json" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to reach the scraper service." }, { status: 502 });
  }
}
