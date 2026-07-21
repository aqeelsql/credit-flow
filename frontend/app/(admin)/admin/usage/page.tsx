"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Coins, Gauge, RefreshCw } from "lucide-react";
import {
  adminFetch,
  numberFromRecord,
  stringFromRecord,
  type AdminAccountDirectoryItem,
  type AdminAccountDirectoryResponse,
  type AdminAccountOverview
} from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

function money(value: number) {
  return `$${value.toFixed(4)}`;
}

export default function UsagePage() {
  const { accessToken, activeAccount, session } = useAuth();
  const [accounts, setAccounts] = useState<AdminAccountDirectoryItem[]>([]);
  const [accountId, setAccountId] = useState(activeAccount?.id ?? "");
  const [overview, setOverview] = useState<AdminAccountOverview | null>(null);
  const [platformOverview, setPlatformOverview] = useState<AdminPlatformOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isSuperAdmin = session?.role === "SuperAdmin";

  const loadAccounts = useCallback(async () => {
    if (!isSuperAdmin) return;
    try {
      const response = await adminFetch<AdminAccountDirectoryResponse>("/accounts?limit=100", accessToken);
      setAccounts(response.items ?? []);
      if (!accountId && response.items?.[0]?.id) setAccountId(response.items[0].id);
    } catch {
      setAccounts([]);
    }
  }, [accessToken, accountId, isSuperAdmin]);

  const isSuperAdmin = session?.role === "SuperAdmin";

  useEffect(() => {
    if (!accountId && activeAccount?.id) setAccountId(activeAccount.id);
  }, [accountId, activeAccount?.id]);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  const loadOverview = useCallback(async () => {
    const targetAccountId = (accountId || activeAccount?.id || "").trim();
    if (!targetAccountId) {
      setError(isSuperAdmin ? "Select an account to load usage." : "No active account selected.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (isSuperAdmin) {
        setPlatformOverview(await adminFetch<AdminPlatformOverview>("/platform/overview?limit=100", accessToken));
        setOverview(null);
      } else {
        const targetAccountId = (accountId || activeAccount?.id || "").trim();
        if (!targetAccountId) throw new Error("No active account selected.");
        setOverview(await adminFetch<AdminAccountOverview>(`/accounts/${encodeURIComponent(targetAccountId)}/overview`, accessToken));
        setPlatformOverview(null);
      }
    } catch (err) {
      setOverview(null);
      setPlatformOverview(null);
      setError(err instanceof Error ? err.message : "Unable to load operations data.");
    } finally {
      setLoading(false);
    }
  }, [accessToken, accountId, activeAccount?.id, isSuperAdmin]);

  useEffect(() => {
    if (accountId || activeAccount?.id) void loadOverview();
  }, [accountId, activeAccount?.id, loadOverview]);

  const selectedAccount = accounts.find((account) => account.id === accountId);
  const totals = useMemo(() => {
    const balance = numberFromRecord(overview?.credits, ["balance", "credits", "available_credits", "remaining_credits"]);
    const quota = numberFromRecord(overview?.usage, ["quota_tokens", "monthly_quota", "limit"]);
    const tokens = numberFromRecord(overview?.usage, ["used_tokens", "tokens_used", "total_tokens", "used", "usage"]);
    const cost = numberFromRecord(overview?.usage, ["total_cost", "cost", "period_cost"]);
    const ratio = quota > 0 ? Math.min(Math.round((tokens / quota) * 100), 100) : 0;
    return { balance, quota, tokens, cost, ratio };
  }, [overview]);

  const platformTotals = platformOverview?.totals ?? {};
  const globalUsage = platformOverview?.global_usage ?? null;
  const platformTokens = numberFromRecord(globalUsage, ["used_tokens", "tokens_used", "total_tokens"]) || Number(platformTotals.tokens_used ?? 0);
  const platformCost = numberFromRecord(globalUsage, ["total_cost", "cost"]) || Number(platformTotals.usage_cost ?? 0);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Ops dashboard</h1>
          <p className="page-subtitle">Live per-account operational view: plan tier, credits, usage, members, and downstream service health.</p>
        </div>
      </div>

      <div className="panel search-row">
        <div className="field">
          <label htmlFor="ops-account">Account</label>
          {isSuperAdmin ? (
            <select id="ops-account" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
              <option value="">Select an account</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.name} - {account.owner_email || account.id}</option>
              ))}
            </select>
          ) : (
            <input id="ops-account" value={accountId} readOnly placeholder="Current account" />
          )}
        </div>
        <button className="button secondary" type="button" onClick={() => void loadOverview()} disabled={loading || !accountId}>
          <RefreshCw className={loading ? "spin" : ""} size={16} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {!isSuperAdmin ? (
        <div className="panel search-row">
          <div className="field">
            <label htmlFor="ops-account">Account ID</label>
            <input id="ops-account" value={accountId} onChange={(event) => setAccountId(event.target.value)} placeholder="Account to inspect" disabled={!!activeAccount?.id} />
          </div>
        </div>
      ) : null}

      {error ? <div className="danger-note with-top-gap">{error}</div> : null}

      <div className="metric-grid with-top-gap">
        <article className="metric-card">
          <Coins size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credit balance</h3>
          <strong>{totals.balance.toLocaleString()}</strong>
          <p>{totals.quota ? `${totals.quota.toLocaleString()} quota` : selectedAccount ? `${selectedAccount.credits.toLocaleString()} account credits` : "Current visible balance."}</p>
        </article>
        <article className="metric-card">
          <Activity size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Tokens used</h3>
          <strong>{totals.tokens.toLocaleString()}</strong>
          <p>${totals.cost.toFixed(4)} model cost recorded.</p>
        </article>
        <article className="metric-card">
          <Gauge size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Usage ratio</h3>
          <strong>{totals.ratio}%</strong>
          <p>Derived from quota and current balance when available.</p>
        </article>
      </div>

      <div className="table-panel with-top-gap">
        <div className="table-header">
          <h2>Account summary</h2>
          <span className="status-badge neutral">{overview ? "Live" : loading ? "Loading" : "No account loaded"}</span>
        </div>
        {overview ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Plan</th>
                <th>Members</th>
                <th>Credits service</th>
                <th>Usage service</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>{stringFromRecord(overview.account, ["name"], selectedAccount?.name ?? overview.account_id)}</strong>
                  <br />
                  <span className="mono">{overview.account_id}</span>
                </td>
                <td>{stringFromRecord(overview.account, ["plan", "tier"], selectedAccount?.plan ?? "Unknown")}</td>
                <td className="mono">{overview.members?.length ?? selectedAccount?.team_size ?? 0}</td>
                <td><span className={overview.errors?.credits ? "status-badge danger" : "status-badge live"}>{overview.errors?.credits ? "Error" : "OK"}</span></td>
                <td><span className={overview.errors?.usage ? "status-badge danger" : "status-badge live"}>{overview.errors?.usage ? "Error" : "OK"}</span></td>
              </tr>
            </tbody>
          </table>
        ) : (
          <div className="empty-state">{loading ? "Loading account overview..." : "Select an account and refresh."}</div>
        )}
      </div>
    </section>
  );
}
