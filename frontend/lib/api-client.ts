type AuthBridge = {
  getAccessToken: () => string | null;
  refreshAccessToken: () => Promise<string | null>;
};

type ApiOptions = RequestInit & {
  skipAuth?: boolean;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, options: ApiOptions = {}, auth?: AuthBridge): Promise<T> {
  const initialToken = auth?.getAccessToken() ?? null;

  const run = async (token: string | null) => {
    const headers = new Headers(options.headers);
    if (!headers.has("Content-Type") && options.body) {
      headers.set("Content-Type", "application/json");
    }
    if (!options.skipAuth && token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    return fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      credentials: "include"
    });
  };

  let response = await run(initialToken);

  if (response.status === 401 && auth && !options.skipAuth) {
    const refreshedToken = await auth.refreshAccessToken();
    if (refreshedToken) {
      response = await run(refreshedToken);
    }
  }

  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { message?: string; error?: string | { message?: string } };
    if (body.message) {
      return body.message;
    }
    if (typeof body.error === "string") {
      return body.error;
    }
    if (typeof body.error === "object" && body.error?.message) {
      return body.error.message;
    }
    return response.statusText;
  } catch {
    return response.statusText;
  }
}

