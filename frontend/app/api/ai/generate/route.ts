import fs from "node:fs";
import path from "node:path";
import { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const ROOT_ENV_PATH = path.resolve(process.cwd(), "..", ".env");
const MAX_LLM_PROMPT_CHARS = 9000;
const DIRECT_LLM_TIMEOUT_MS = 90000;

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function readRootEnv(name: string) {
  const direct = process.env[name];
  if (direct) return direct.trim();
  try {
    const content = fs.readFileSync(ROOT_ENV_PATH, "utf8");
    const line = content.split(/\r?\n/).find((item) => item.trimStart().startsWith(`${name}=`));
    if (!line) return "";
    const value = line.slice(line.indexOf("=") + 1).trim();
    return value.replace(/^(?:(['"])(.*)\1)$/, "$2").trim();
  } catch {
    return "";
  }
}

function streamHeaders(contentType = "text/event-stream; charset=utf-8") {
  return {
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "Content-Type": contentType,
    "X-Accel-Buffering": "no"
  };
}

async function gatewayStream(request: NextRequest, prompt: string, accountId: string | null) {
  if (!API_BASE_URL) return null;
  const upstreamUrl = new URL("/content/generate/stream", API_BASE_URL);
  if (accountId) upstreamUrl.searchParams.set("account_id", accountId);
  upstreamUrl.searchParams.set("prompt", prompt);

  const headers = new Headers({ Accept: "text/event-stream" });
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.set("Authorization", authorization);
  if (cookie) headers.set("Cookie", cookie);

  const upstream = await fetch(upstreamUrl, { headers, cache: "no-store" });
  if (!upstream.ok || !upstream.body) return null;
  return new Response(upstream.body, { status: upstream.status, headers: streamHeaders(upstream.headers.get("content-type") ?? undefined) });
}

async function directOpenRouterStream(prompt: string) {
  const apiKey = readRootEnv("OPENROUTER_API_KEY");
  const model = readRootEnv("OPENROUTER_MODEL") || readRootEnv("AI_GENERATION_OPENROUTER_MODEL") || "openrouter/free";
  const baseUrl = readRootEnv("OPENROUTER_BASE_URL") || "https://openrouter.ai/api/v1";
  if (!apiKey) {
    return Response.json({ error: "Gateway is unavailable and OPENROUTER_API_KEY is not configured." }, { status: 502 });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DIRECT_LLM_TIMEOUT_MS);
  const upstream = await fetch(`${baseUrl.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    signal: controller.signal,
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "HTTP-Referer": "http://localhost:3000",
      "X-Title": "CreditFlow"
    },
    body: JSON.stringify({
      model,
      stream: true,
      messages: [
        { role: "system", content: "You write polished, factual social media posts from provided scraped research. Do not invent facts." },
        { role: "user", content: prompt.slice(0, MAX_LLM_PROMPT_CHARS) }
      ]
    })
  }).finally(() => clearTimeout(timeout));

  if (!upstream.ok || !upstream.body) {
    const message = await upstream.text().catch(() => "");
    return Response.json({ error: message || `Direct LLM request failed (${upstream.status}).` }, { status: upstream.status || 502 });
  }

  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const stream = new ReadableStream({
    async start(controller) {
      const reader = upstream.body!.getReader();
      let buffer = "";
      try {
        while (true) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
            if (!data) continue;
            if (data === "[DONE]") {
              controller.enqueue(encoder.encode("data: [DONE]\n\n"));
              controller.close();
              return;
            }
            try {
              const payload = JSON.parse(data) as { choices?: Array<{ delta?: { content?: string } }> };
              const token = payload.choices?.[0]?.delta?.content;
              if (token) controller.enqueue(encoder.encode(`data: ${JSON.stringify({ token })}\n\n`));
            } catch {
              // Ignore provider keepalive or malformed frames.
            }
          }
          if (done) break;
        }
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      } catch (error) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ event: "error", message: error instanceof Error ? error.message : "Direct LLM stream failed." })}\n\n`));
        controller.close();
      }
    }
  });

  return new Response(stream, { status: 200, headers: streamHeaders() });
}

export async function GET(request: NextRequest) {
  const accountId = request.nextUrl.searchParams.get("account_id");
  const prompt = request.nextUrl.searchParams.get("prompt")?.trim();
  if (!prompt) {
    return Response.json({ error: "Prompt is required." }, { status: 400 });
  }

  try {
    const gateway = await gatewayStream(request, prompt.slice(0, MAX_LLM_PROMPT_CHARS), accountId);
    if (gateway) return gateway;
  } catch {
    // Fall back to direct local-dev LLM streaming below.
  }

  try {
    return await directOpenRouterStream(prompt.slice(0, MAX_LLM_PROMPT_CHARS));
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unable to reach the generation gateway or direct LLM provider." }, { status: 502 });
  }
}
