import { NextRequest } from "next/server";
import { proxyScraperRequest } from "../../_proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest, { params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = await params;
  return proxyScraperRequest(request, `/documents/${encodeURIComponent(documentId)}`);
}
