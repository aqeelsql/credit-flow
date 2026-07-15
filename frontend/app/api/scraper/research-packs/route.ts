import { NextRequest } from "next/server";
import { proxyScraperRequest } from "../_proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const upstreamUrl = new URL("http://local/research-packs");
  const limit = request.nextUrl.searchParams.get("limit");
  if (limit) upstreamUrl.searchParams.set("limit", limit);
  return proxyScraperRequest(request, `${upstreamUrl.pathname}${upstreamUrl.search}`);
}
