"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Account, AccountRole, AccountType, SessionPayload } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type SignupResponse = {
  status: string;
  user_id: string;
  account_id?: string | null;
  message: string;
  access_token?: string | null;
  expires_in?: number | null;
  role?: AccountRole | null;
  jti?: string | null;
};

type TokenResponse = {
  access_token: string;
  expires_in: number;
  user_id: string;
  account_id: string;
  role: AccountRole;
  jti: string;
};

type AccountResponse = {
  id: string;
  name: string;
  type: AccountType;
  role: AccountRole;
  plan: string;
  credits: number;
  teamSize?: number;
  team_size?: number;
};

type PendingInvite = {
  code: string;
  email: string;
};

type AuthContextValue = {
  status: AuthStatus;
  accessToken: string | null;
  session: SessionPayload | null;
  accounts: Account[];
  activeAccount: Account | null;
  login: (email: string, password: string, preferredRole?: AccountRole) => Promise<AccountRole>;
  signup: (email: string, password: string, accountName?: string, inviteCode?: string) => Promise<SignupResponse>;
  logout: () => void;
  switchAccount: (accountId: string) => Promise<void>;
  createAccount: (type: Exclude<AccountType, "platform">, name: string) => Promise<void>;
  acceptInvite: (code: string) => Promise<void>;
  refreshAccessToken: () => Promise<string | null>;
};

const ACCESS_TOKEN_STORAGE_KEY = "creditflow.accessToken";
const ACCOUNTS_STORAGE_KEY = "creditflow.accounts";
const PENDING_INVITE_STORAGE_KEY = "creditflow.pendingInviteCode";
const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const platformAccount: Account = {
  id: "platform",
  name: "CreditFlow Platform",
  type: "platform",
  role: "SuperAdmin",
  plan: "Platform",
  credits: 0,
  teamSize: 0
};

function safeStorageGet(key: string): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(key);
}

function safeStorageSet(key: string, value: string) {
  if (typeof window !== "undefined") window.localStorage.setItem(key, value);
}

function safeStorageRemove(key: string) {
  if (typeof window !== "undefined") window.localStorage.removeItem(key);
}

function decodeJwtPayload(token: string): SessionPayload | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    const json = decodeURIComponent(
      Array.from(atob(padded))
        .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`)
        .join("")
    );
    return JSON.parse(json) as SessionPayload;
  } catch {
    return null;
  }
}

async function readApiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { message?: string; error?: string | { message?: string } };
    if (body.message) return body.message;
    if (typeof body.error === "string") return body.error;
    if (typeof body.error === "object" && body.error?.message) return body.error.message;
  } catch {
    // Use status text below.
  }
  return response.statusText || "Request failed.";
}

async function appRequest<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...init, headers, credentials: "include", cache: "no-store" });
  if (!response.ok) throw new Error(await readApiError(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function normalizeAccount(row: AccountResponse): Account {
  return {
    id: row.id,
    name: row.name,
    type: row.type,
    role: row.role,
    plan: row.plan,
    credits: row.credits,
    teamSize: row.teamSize ?? row.team_size ?? 1
  };
}

function accountFromToken(payload: SessionPayload | null): Account | null {
  if (!payload) return null;
  if (payload.role === "SuperAdmin") return platformAccount;
  return {
    id: payload.account_id,
    name: payload.account_id,
    type: "individual",
    role: payload.role,
    plan: "Unknown",
    credits: 0,
    teamSize: 1
  };
}

function readStoredAccounts(): Account[] {
  try {
    const raw = safeStorageGet(ACCOUNTS_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Account[]) : [];
  } catch {
    return [];
  }
}

function writeStoredAccounts(accounts: Account[]) {
  safeStorageSet(ACCOUNTS_STORAGE_KEY, JSON.stringify(accounts));
}

function readPendingInvite(): PendingInvite | null {
  const raw = safeStorageGet(PENDING_INVITE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PendingInvite>;
    if (parsed.code && parsed.email) return { code: parsed.code, email: parsed.email.toLowerCase() };
  } catch {
    // Old invite-code-only values are unsafe because they are not tied to an email.
  }
  safeStorageRemove(PENDING_INVITE_STORAGE_KEY);
  return null;
}

function upsertAccount(accounts: Account[], account: Account): Account[] {
  const index = accounts.findIndex((item) => item.id === account.id);
  if (index === -1) return [...accounts, account];
  return accounts.map((item) => (item.id === account.id ? account : item));
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);

  const setToken = useCallback((token: string | null) => {
    setAccessToken(token);
    setSession(token ? decodeJwtPayload(token) : null);
    setStatus(token ? "authenticated" : "unauthenticated");
    if (token) safeStorageSet(ACCESS_TOKEN_STORAGE_KEY, token);
    else safeStorageRemove(ACCESS_TOKEN_STORAGE_KEY);
  }, []);

  const loadAccounts = useCallback(async (token: string | null) => {
    if (!token) return [];
    try {
      const rows = await appRequest<AccountResponse[]>("/api/accounts", token);
      const normalized = rows.map(normalizeAccount);
      setAccounts(normalized);
      writeStoredAccounts(normalized);
      return normalized;
    } catch {
      return readStoredAccounts();
    }
  }, []);

  useEffect(() => {
    const token = safeStorageGet(ACCESS_TOKEN_STORAGE_KEY);
    const storedAccounts = readStoredAccounts();
    setAccounts(storedAccounts);
    if (!token) {
      setStatus("unauthenticated");
      return;
    }
    const payload = decodeJwtPayload(token);
    if (!payload || payload.exp * 1000 <= Date.now()) {
      safeStorageRemove(ACCESS_TOKEN_STORAGE_KEY);
      setStatus("unauthenticated");
      return;
    }
    const fallbackAccount = accountFromToken(payload);
    if (fallbackAccount && fallbackAccount.role !== "SuperAdmin" && !storedAccounts.some((account) => account.id === fallbackAccount.id)) {
      const next = upsertAccount(storedAccounts, fallbackAccount);
      setAccounts(next);
      writeStoredAccounts(next);
    }
    setToken(token);
    void loadAccounts(token);
  }, [loadAccounts, setToken]);

  const activeAccount = useMemo(() => {
    if (!session || session.role === "SuperAdmin") return null;
    return accounts.find((account) => account.id === session.account_id) ?? accountFromToken(session);
  }, [accounts, session]);

  const refreshAccessToken = useCallback(async () => {
    try {
      const response = await appRequest<TokenResponse>("/api/auth/refresh", accessToken, { method: "POST", body: JSON.stringify({}) });
      setToken(response.access_token);
      void loadAccounts(response.access_token);
      return response.access_token;
    } catch {
      safeStorageRemove(ACCESS_TOKEN_STORAGE_KEY);
      setToken(null);
      return null;
    }
  }, [accessToken, loadAccounts, setToken]);

  useEffect(() => {
    if (!session || !accessToken) return;
    const refreshInMs = Math.max(session.exp * 1000 - Date.now() - 60_000, 5_000);
    const timer = window.setTimeout(() => {
      void refreshAccessToken();
    }, refreshInMs);
    return () => window.clearTimeout(timer);
  }, [accessToken, refreshAccessToken, session]);

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await appRequest<TokenResponse>("/api/auth/login", null, {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password })
      });
      setToken(response.access_token);
      let currentToken = response.access_token;
      let currentRole = response.role;
      await loadAccounts(currentToken);

      const pendingInvite = readPendingInvite();
      const loginEmail = email.trim().toLowerCase();
      if (pendingInvite && pendingInvite.email !== loginEmail) {
        safeStorageRemove(PENDING_INVITE_STORAGE_KEY);
      }
      if (pendingInvite && pendingInvite.email === loginEmail && response.role !== "SuperAdmin") {
        const account = await appRequest<AccountResponse>("/api/accounts/invites/accept", currentToken, {
          method: "POST",
          body: JSON.stringify({ code: pendingInvite.code })
        });
        const normalized = normalizeAccount(account);
        const next = upsertAccount(readStoredAccounts(), normalized);
        setAccounts(next);
        writeStoredAccounts(next);
        const switched = await appRequest<TokenResponse>("/api/auth/switch-account", currentToken, {
          method: "POST",
          body: JSON.stringify({ account_id: normalized.id })
        });
        currentToken = switched.access_token;
        currentRole = switched.role;
        setToken(currentToken);
        await loadAccounts(currentToken);
        safeStorageRemove(PENDING_INVITE_STORAGE_KEY);
      }
      return currentRole;
    },
    [loadAccounts, setToken]
  );

  const signup = useCallback(async (email: string, password: string, accountName?: string, inviteCode?: string) => {
    const response = await appRequest<SignupResponse>("/api/auth/signup", null, {
      method: "POST",
      body: JSON.stringify({ email: email.trim(), password, account_name: accountName || undefined, invite_code: inviteCode || undefined })
    });
    if (response.access_token) {
      setToken(response.access_token);
      await loadAccounts(response.access_token);
    }
    return response;
  }, [loadAccounts, setToken]);

  const logout = useCallback(() => {
    void appRequest("/api/auth/logout", accessToken, { method: "POST", body: JSON.stringify({}) }).catch(() => undefined);
    safeStorageRemove(ACCESS_TOKEN_STORAGE_KEY);
    safeStorageRemove(ACCOUNTS_STORAGE_KEY);
    safeStorageRemove(PENDING_INVITE_STORAGE_KEY);
    setAccounts([]);
    setToken(null);
  }, [accessToken, setToken]);

  const switchAccount = useCallback(
    async (accountId: string) => {
      const response = await appRequest<TokenResponse>("/api/auth/switch-account", accessToken, {
        method: "POST",
        body: JSON.stringify({ account_id: accountId })
      });
      setToken(response.access_token);
      await loadAccounts(response.access_token);
    },
    [accessToken, loadAccounts, setToken]
  );

  const createAccount = useCallback(
    async (type: Exclude<AccountType, "platform">, name: string) => {
      const account = await appRequest<AccountResponse>("/api/accounts", accessToken, {
        method: "POST",
        body: JSON.stringify({ type, name })
      });
      const normalized = normalizeAccount(account);
      const next = upsertAccount(accounts, normalized);
      setAccounts(next);
      writeStoredAccounts(next);
      await switchAccount(normalized.id);
    },
    [accessToken, accounts, switchAccount]
  );

  const acceptInvite = useCallback(
    async (code: string) => {
      const account = await appRequest<AccountResponse>("/api/accounts/invites/accept", accessToken, {
        method: "POST",
        body: JSON.stringify({ code })
      });
      const normalized = normalizeAccount(account);
      const next = upsertAccount(accounts, normalized);
      setAccounts(next);
      writeStoredAccounts(next);
      await switchAccount(normalized.id);
    },
    [accessToken, accounts, switchAccount]
  );

  const value = useMemo(
    () => ({ status, accessToken, session, accounts, activeAccount, login, signup, logout, switchAccount, createAccount, acceptInvite, refreshAccessToken }),
    [status, accessToken, session, accounts, activeAccount, login, signup, logout, switchAccount, createAccount, acceptInvite, refreshAccessToken]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export function useRequireAuth(allowedRoles: AccountRole[], requireAccount = true) {
  const router = useRouter();
  const auth = useAuth();

  useEffect(() => {
    if (auth.status === "loading") return;
    if (auth.status === "unauthenticated") {
      const next = encodeURIComponent(window.location.pathname);
      router.replace(`/login?next=${next}`);
      return;
    }
    if (requireAccount && !auth.activeAccount && auth.session?.role !== "SuperAdmin") {
      router.replace("/create-or-join");
      return;
    }
    if (auth.session && !allowedRoles.includes(auth.session.role)) router.replace("/unauthorized");
  }, [allowedRoles, auth.activeAccount, auth.session, auth.status, requireAccount, router]);

  const isAllowed = auth.status === "authenticated" && !!auth.session && allowedRoles.includes(auth.session.role) && (!requireAccount || !!auth.activeAccount || auth.session.role === "SuperAdmin");
  return { ...auth, isAllowed };
}
