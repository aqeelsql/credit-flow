export type AdminSession = {
  jti: string;
  user_id?: string | null;
  account_id?: string | null;
  role?: string | null;
  ttl_seconds?: number | null;
};

export type AdminAuditItem = {
  id: string;
  event_id: string;
  routing_key: string;
  exchange?: string | null;
  account_id?: string | null;
  actor_user_id?: string | null;
  action: string;
  summary?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AdminAuditResponse = {
  items: AdminAuditItem[];
};


export type AdminAccountRow = {
  id: string;
  name: string;
  type: string;
  plan: string;
  credits: number;
  owner_user_id?: string | null;
  owner_email?: string | null;
  team_size: number;
  credit_balance?: number | null;
  low_balance_threshold?: number | null;
  is_low_balance?: boolean | null;
  tokens_used?: number | null;
  usage_cost?: number | string | null;
  usage_period?: string | null;
  quota_tokens?: number | null;
  sync_errors?: Record<string, string>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type AdminPlatformOverview = {
  accounts: AdminAccountRow[];
  totals: Record<string, number>;
  global_usage?: Record<string, unknown> | null;
  errors?: Record<string, string>;
};
export type AdminAccountOverview = {
  account_id: string;
  account?: Record<string, unknown> | null;
  credits?: Record<string, unknown> | null;
  usage?: Record<string, unknown> | null;
  members?: Record<string, unknown>[] | null;
  errors?: Record<string, string>;
};

export type AdminAccountDirectoryItem = {
  id: string;
  name: string;
  type: string;
  plan: string;
  credits: number;
  team_size: number;
  owner_name?: string | null;
  owner_email?: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminOpsSummary = {
  total_credits_generated: number;
  total_credits_sold: number;
  credits_left: number;
  active_package_credits: number;
  package_count: number;
  active_package_count: number;
  total_money_generated_cents: number;
  currency: string;
  purchase_count: number;
  account_count: number;
  errors?: Record<string, string>;
};
export type AdminAccountDirectoryResponse = {
  items: AdminAccountDirectoryItem[];
  errors?: Record<string, string>;
};

export class AdminApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string | { message?: string }; message?: string };
    if (body.message) return body.message;
    if (typeof body.error === "string") return body.error;
    if (typeof body.error === "object" && body.error?.message) return body.error.message;
  } catch {
    // Ignore JSON parse failures and use the HTTP status text below.
  }
  return response.statusText || "Admin request failed.";
}

export async function adminFetch<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const response = await fetch(`/api/admin${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    throw new AdminApiError(await readError(response), response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function compactId(value?: string | null, size = 10) {
  if (!value) return "—";
  return value.length > size + 4 ? `${value.slice(0, size)}…${value.slice(-4)}` : value;
}

export function numberFromRecord(record: Record<string, unknown> | null | undefined, keys: string[]) {
  for (const key of keys) {
    const value = record?.[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return 0;
}

export function stringFromRecord(record: Record<string, unknown> | null | undefined, keys: string[], fallback = "—") {
  for (const key of keys) {
    const value = record?.[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number") return String(value);
  }
  return fallback;
}


