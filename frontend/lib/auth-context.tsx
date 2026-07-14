"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { decodeJwtPayload, demoAccounts, makeMockJwt, platformAccount } from "@/lib/mock-data";
import type { Account, AccountRole, AccountType, SessionPayload } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type SignupResponse = {
  status: string;
  user_id: string;
  account_id?: string | null;
  message: string;
};

type StoredSession = {
  identity: string;
  accountId: string;
  role: AccountRole;
};

type AuthContextValue = {
  status: AuthStatus;
  accessToken: string | null;
  session: SessionPayload | null;
  accounts: Account[];
  activeAccount: Account | null;
  login: (email: string, password: string, preferredRole?: AccountRole) => Promise<void>;
  signup: (email: string, password: string, accountName?: string) => Promise<SignupResponse>;
  logout: () => void;
  switchAccount: (accountId: string) => Promise<void>;
  createAccount: (type: Exclude<AccountType, "platform">, name: string) => Promise<void>;
  acceptInvite: (code: string) => Promise<void>;
  refreshAccessToken: () => Promise<string | null>;
};

const SESSION_STORAGE_KEY = "creditflow.localSession";
const ACCOUNTS_STORAGE_KEY = "creditflow.localAccounts";
const USE_LOCAL_AUTH = process.env.NEXT_PUBLIC_USE_LOCAL_AUTH !== "false";
const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const onboardingAccount: Account = {
  id: "onboarding",
  name: "Choose account",
  type: "individual",
  role: "Owner",
  plan: "Starter",
  credits: 0,
  teamSize: 0
};

function safeStorageGet(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(key);
}

function safeStorageSet(key: string, value: string) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(key, value);
  }
}

function safeStorageRemove(key: string) {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(key);
  }
}

function accountIdFromIdentity(identity: string): string {
  const cleaned = identity.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return `local_${cleaned || "guest"}`;
}

function displayNameFromIdentity(identity: string): string {
  const value = identity.trim();
  if (!value) {
    return "Demo Studio";
  }
  const [firstPart] = value.split("@");
  return `${firstPart || "Demo"}'s Studio`;
}

function createLocalAccount(identity: string, name?: string, type: Exclude<AccountType, "platform"> = "individual", role: Exclude<AccountRole, "SuperAdmin"> = "Owner"): Account {
  return {
    id: type === "individual" ? accountIdFromIdentity(identity) : `local_team_${Date.now()}`,
    name: name?.trim() || displayNameFromIdentity(identity),
    type,
    role,
    plan: "Starter",
    credits: 1000,
    teamSize: type === "team" ? 2 : 1
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

function readStoredSession(): StoredSession | null {
  try {
    const raw = safeStorageGet(SESSION_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    return null;
  }
}

function writeStoredSession(session: StoredSession) {
  safeStorageSet(SESSION_STORAGE_KEY, JSON.stringify(session));
}

function clearStoredSession() {
  safeStorageRemove(SESSION_STORAGE_KEY);
}

function upsertAccount(accounts: Account[], account: Account): Account[] {
  const index = accounts.findIndex((item) => item.id === account.id);
  if (index === -1) {
    return [...accounts, account];
  }
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
  }, []);

  const issueToken = useCallback(
    (account: Account, identity: string) => {
      const token = makeMockJwt(account, identity.trim() || "guest@creditflow.test");
      setToken(token);
      return token;
    },
    [setToken]
  );

  const enterWithAccount = useCallback(
    (account: Account, identity: string, nextAccounts?: Account[]) => {
      const mergedAccounts = upsertAccount(nextAccounts ?? readStoredAccounts(), account);
      setAccounts(mergedAccounts);
      writeStoredAccounts(mergedAccounts);
      writeStoredSession({ identity: identity.trim() || "guest@creditflow.test", accountId: account.id, role: account.role });
      return issueToken(account, identity);
    },
    [issueToken]
  );

  const enterOnboarding = useCallback(
    (identity: string) => {
      const nextIdentity = identity.trim() || "guest@creditflow.test";
      setAccounts(readStoredAccounts());
      writeStoredSession({ identity: nextIdentity, accountId: onboardingAccount.id, role: onboardingAccount.role });
      return issueToken(onboardingAccount, nextIdentity);
    },
    [issueToken]
  );

  const enterPlatform = useCallback(
    (identity: string) => {
      const nextIdentity = identity.trim() || "admin@creditflow.test";
      setAccounts(readStoredAccounts());
      writeStoredSession({ identity: nextIdentity, accountId: platformAccount.id, role: "SuperAdmin" });
      return issueToken(platformAccount, nextIdentity);
    },
    [issueToken]
  );

  useEffect(() => {
    const storedAccounts = readStoredAccounts();
    const storedSession = readStoredSession();
    setAccounts(storedAccounts);

    if (!storedSession) {
      if (USE_LOCAL_AUTH) {
        const defaultAccount = demoAccounts[0];
        const nextAccounts = storedAccounts.length ? storedAccounts : demoAccounts;
        setAccounts(nextAccounts);
        writeStoredAccounts(nextAccounts);
        writeStoredSession({ identity: "raja@example.com", accountId: defaultAccount.id, role: defaultAccount.role });
        issueToken(defaultAccount, "raja@example.com");
        return;
      }

      setStatus("unauthenticated");
      return;
    }

    if (storedSession.role === "SuperAdmin") {
      issueToken(platformAccount, storedSession.identity);
      return;
    }

    if (storedSession.accountId === onboardingAccount.id) {
      issueToken(onboardingAccount, storedSession.identity);
      return;
    }

    const storedAccount = storedAccounts.find((account) => account.id === storedSession.accountId);
    if (storedAccount) {
      issueToken(storedAccount, storedSession.identity);
      return;
    }

    const repairedAccount = {
      ...createLocalAccount(storedSession.identity, undefined, "individual", storedSession.role as Exclude<AccountRole, "SuperAdmin">),
      id: storedSession.accountId
    };
    const repairedAccounts = upsertAccount(storedAccounts, repairedAccount);
    setAccounts(repairedAccounts);
    writeStoredAccounts(repairedAccounts);
    issueToken(repairedAccount, storedSession.identity);
  }, [issueToken]);

  const activeAccount = useMemo(() => {
    if (!session || session.role === "SuperAdmin" || session.account_id === "onboarding") {
      return null;
    }
    return accounts.find((account) => account.id === session.account_id) ?? null;
  }, [accounts, session]);

  const refreshAccessToken = useCallback(async () => {
    if (!session) {
      return null;
    }

    if (session.role === "SuperAdmin") {
      return issueToken(platformAccount, session.email ?? "admin@creditflow.test");
    }

    if (session.account_id === onboardingAccount.id) {
      return issueToken(onboardingAccount, session.email ?? "guest@creditflow.test");
    }

    const account = accounts.find((item) => item.id === session.account_id);
    if (!account) {
      setToken(null);
      clearStoredSession();
      return null;
    }

    return issueToken(account, session.email ?? "guest@creditflow.test");
  }, [accounts, issueToken, session, setToken]);

  useEffect(() => {
    if (!session || !accessToken) {
      return;
    }

    const refreshInMs = Math.max(session.exp * 1000 - Date.now() - 60_000, 5_000);
    const timer = window.setTimeout(() => {
      void refreshAccessToken();
    }, refreshInMs);

    return () => window.clearTimeout(timer);
  }, [accessToken, refreshAccessToken, session]);

  const login = useCallback(
    async (email: string, _password: string, preferredRole: AccountRole = "Owner") => {
      const identity = email.trim() || "guest@creditflow.test";
      if (preferredRole === "SuperAdmin") {
        enterPlatform(identity);
        return;
      }

      const account = createLocalAccount(identity, undefined, "individual", preferredRole);
      enterWithAccount(account, identity);
    },
    [enterPlatform, enterWithAccount]
  );

  const signup = useCallback(
    async (email: string, _password: string, _accountName?: string) => {
      const identity = email.trim() || "guest@creditflow.test";
      enterOnboarding(identity);
      return {
        status: "onboarding",
        user_id: "local_user",
        account_id: null,
        message: "Choose or join an account."
      };
    },
    [enterOnboarding]
  );

  const logout = useCallback(() => {
    clearStoredSession();
    setToken(null);
  }, [setToken]);

  const switchAccount = useCallback(
    async (accountId: string) => {
      const account = accounts.find((item) => item.id === accountId);
      if (!account) {
        return;
      }
      enterWithAccount(account, session?.email ?? "guest@creditflow.test", accounts);
    },
    [accounts, enterWithAccount, session]
  );

  const createAccount = useCallback(
    async (type: Exclude<AccountType, "platform">, name: string) => {
      const identity = session?.email ?? "guest@creditflow.test";
      const account = createLocalAccount(identity, name || (type === "team" ? "New Team" : "My Studio"), type, "Owner");
      enterWithAccount(account, identity, accounts);
    },
    [accounts, enterWithAccount, session]
  );

  const acceptInvite = useCallback(
    async (code: string) => {
      const identity = session?.email ?? "guest@creditflow.test";
      const inviteName = code.trim() ? `Invited Team ${code.trim()}` : "Invited Team";
      const account = createLocalAccount(identity, inviteName, "team", "Member");
      enterWithAccount(account, identity, accounts);
    },
    [accounts, enterWithAccount, session]
  );

  const value = useMemo(
    () => ({
      status,
      accessToken,
      session,
      accounts,
      activeAccount,
      login,
      signup,
      logout,
      switchAccount,
      createAccount,
      acceptInvite,
      refreshAccessToken
    }),
    [
      status,
      accessToken,
      session,
      accounts,
      activeAccount,
      login,
      signup,
      logout,
      switchAccount,
      createAccount,
      acceptInvite,
      refreshAccessToken
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}

export function useRequireAuth(allowedRoles: AccountRole[], requireAccount = true) {
  const router = useRouter();
  const auth = useAuth();

  useEffect(() => {
    if (auth.status === "loading") {
      return;
    }

    if (auth.status === "unauthenticated") {
      const next = encodeURIComponent(window.location.pathname);
      router.replace(`/login?next=${next}`);
      return;
    }

    if (requireAccount && !auth.activeAccount && auth.session?.role !== "SuperAdmin") {
      router.replace("/create-or-join");
      return;
    }

    if (auth.session && !allowedRoles.includes(auth.session.role)) {
      router.replace("/unauthorized");
    }
  }, [allowedRoles, auth.activeAccount, auth.session, auth.status, requireAccount, router]);

  const isAllowed =
    auth.status === "authenticated" &&
    !!auth.session &&
    allowedRoles.includes(auth.session.role) &&
    (!requireAccount || !!auth.activeAccount || auth.session.role === "SuperAdmin");

  return {
    ...auth,
    isAllowed
  };
}
