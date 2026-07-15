type StreamGenerationArgs = {
  prompt: string;
  accountId: string;
  accessToken: string | null;
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
};

const USE_MOCK_AI = process.env.NEXT_PUBLIC_USE_MOCK_AI !== "false";

export function streamAiGeneration({
  prompt,
  accountId,
  accessToken,
  onToken,
  onDone,
  onError
}: StreamGenerationArgs): () => void {
  if (USE_MOCK_AI) {
    return mockTokenStream(prompt, onToken, onDone);
  }

  const params = new URLSearchParams({
    account_id: accountId,
    prompt
  });

  const controller = new AbortController();
  void consumeGenerationStream(
    `/api/ai/generate?${params.toString()}`,
    accessToken,
    controller.signal,
    onToken,
    onDone,
    onError
  );
  return () => controller.abort();
}

async function consumeGenerationStream(
  url: string,
  accessToken: string | null,
  signal: AbortSignal,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (message: string) => void
) {
  try {
    const headers = new Headers({ Accept: "text/event-stream" });
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
    const response = await fetch(url, { headers, credentials: "include", signal });
    if (!response.ok || !response.body) {
      const body = (await response.json().catch(() => null)) as { error?: string | { message?: string } } | null;
      const error = typeof body?.error === "string" ? body.error : body?.error?.message;
      throw new Error(error || `Generation request failed (${response.status}).`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;
    while (!finished) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (!data) continue;
        if (data === "[DONE]") {
          finished = true;
          onDone();
          break;
        }
        try {
          const payload = JSON.parse(data) as { event?: string; token?: string; message?: string };
          if (payload.event === "error") {
            throw new Error(payload.message || "Text generation failed.");
          }
          if (payload.token) onToken(payload.token);
        } catch (error) {
          if (error instanceof SyntaxError) onToken(data);
          else throw error;
        }
      }
      if (done && !finished) {
        throw new Error("The generation stream closed unexpectedly.");
      }
    }
  } catch (error) {
    if (!signal.aborted) {
      onError(error instanceof Error ? error.message : "The generation stream closed unexpectedly.");
    }
  }
}

function mockTokenStream(prompt: string, onToken: (token: string) => void, onDone: () => void): () => void {
  const cleanPrompt = prompt.trim() || "a practical launch post for a credit-based AI publishing workflow";
  const text = `Drafting for: ${cleanPrompt}\n\nCreditFlow helps teams turn a raw idea into a scheduled LinkedIn post without losing account-level control. Start with the audience pain, show the measurable credit cost, then close with a direct publishing cue. Keep the voice crisp, useful, and confident.`;
  const tokens = text.split(/(\s+)/);
  let index = 0;

  const interval = window.setInterval(() => {
    onToken(tokens[index] ?? "");
    index += 1;
    if (index >= tokens.length) {
      window.clearInterval(interval);
      onDone();
    }
  }, 34);

  return () => window.clearInterval(interval);
}
