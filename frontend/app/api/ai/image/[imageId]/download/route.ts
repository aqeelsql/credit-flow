import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest, { params }: { params: Promise<{ imageId: string }> }) {
  if (!API_BASE_URL) {
    return Response.json({ error: "Gateway API URL is not configured." }, { status: 500 });
  }

  const { imageId } = await params;
  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);

  try {
    const upstream = await fetch(`${API_BASE_URL}/content/generate/image/${encodeURIComponent(imageId)}/download`, {
      headers,
      cache: "no-store"
    });
    const responseHeaders = new Headers();
    const contentType = upstream.headers.get("content-type");
    const disposition = upstream.headers.get("content-disposition");
    if (contentType) responseHeaders.set("Content-Type", contentType);
    if (disposition) responseHeaders.set("Content-Disposition", disposition);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "Unable to download the generated image." },
      { status: 502 }
    );
  }
}
