import { NextRequest } from "next/server";
import { proxyScraperRequest } from "../../../_proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest, { params }: { params: Promise<{ packId: string }> }) {
  const { packId } = await params;
  return proxyScraperRequest(request, `/research-packs/${encodeURIComponent(packId)}/generate-post`, { method: "POST", body: await request.text() });
}
