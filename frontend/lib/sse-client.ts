type StreamGenerationArgs = {
  prompt: string;
  accountId: string;
  requestId?: string;
  accessToken: string | null;
  onToken: (token: string) => void;
  onJobId?: (jobId: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
};

export function streamAiGeneration({
  prompt,
  accountId,
  requestId,
  accessToken,
  onToken,
  onJobId,
  onDone,
  onError
}: StreamGenerationArgs): () => void {
  const params = new URLSearchParams({
    account_id: accountId,
    prompt
  });
  if (requestId) params.set("request_id", requestId);

  const controller = new AbortController();
  void consumeGenerationStream(
    `/api/ai/generate?${params.toString()}`,
    accessToken,
    controller.signal,
    onToken,
    onJobId,
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
  onJobId: ((jobId: string) => void) | undefined,
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
          const payload = JSON.parse(data) as { event?: string; token?: string; message?: string; job_id?: string };
          if (payload.event === "error") {
            throw new Error(payload.message || "Text generation failed.");
          }
          if (payload.job_id) onJobId?.(payload.job_id);
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
