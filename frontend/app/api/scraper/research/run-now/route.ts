import { NextRequest } from "next/server";
import { proxyScraperRequest } from "../../_proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  return proxyScraperRequest(request, "/research/run-now", { method: "POST", body: await request.text() });
}
