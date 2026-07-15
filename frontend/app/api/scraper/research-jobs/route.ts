import { NextRequest } from "next/server";
import { proxyScraperRequest } from "../_proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const upstreamUrl = new URL("http://local/research-jobs");
  const limit = request.nextUrl.searchParams.get("limit");
  if (limit) upstreamUrl.searchParams.set("limit", limit);
  return proxyScraperRequest(request, `${upstreamUrl.pathname}${upstreamUrl.search}`);
}

export async function POST(request: NextRequest) {
  return proxyScraperRequest(request, "/research-jobs", { method: "POST", body: await request.text() });
}
