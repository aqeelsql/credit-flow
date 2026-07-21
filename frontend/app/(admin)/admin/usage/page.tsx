"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Coins, Gauge, RefreshCw, Users } from "lucide-react";
import { adminFetch, numberFromRecord, stringFromRecord, type AdminAccountOverview, type AdminPlatformOverview } from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

function money(value: number) {
  return `$${value.toFixed(4)}`;
}

export default function UsagePage() {
  const { accessToken, activeAccount, session } = useAuth();
  const [accountId, setAccountId] = useState(activeAccount?.id ?? "");
  const [overview, setOverview] = useState<AdminAccountOverview | null>(null);
  const [platformOverview, setPlatformOverview] = useState<AdminPlatformOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSuperAdmin = session?.role === "SuperAdmin";

  useEffect(() => {
    if (!accountId && activeAccount?.id) setAccountId(activeAccount.id);
  }, [accountId, activeAccount?.id]);

  const loadData = useCallback(async () => {
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
    void loadData();
  }, [loadData]);

  const accountTotals = useMemo(() => {
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
          <p className="page-subtitle">{isSuperAdmin ? "Platform-wide credits, AI usage, accounts, and sync health." : "Per-account operational view for your tenant."}</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void loadData()} disabled={loading}>
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

      {isSuperAdmin ? (
        <>
          <div className="metric-grid with-top-gap">
            <article className="metric-card"><Gauge size={22} color="var(--color-primary)" aria-hidden="true" /><h3>Accounts</h3><strong>{Number(platformTotals.accounts ?? 0).toLocaleString()}</strong><p>{Number(platformTotals.accounts_with_errors ?? 0).toLocaleString()} with sync issues.</p></article>
            <article className="metric-card"><Coins size={22} color="var(--color-primary)" aria-hidden="true" /><h3>Total credits</h3><strong>{Number(platformTotals.credit_balance ?? 0).toLocaleString()}</strong><p>Summed from Credits ledger balances.</p></article>
            <article className="metric-card"><Activity size={22} color="var(--color-primary)" aria-hidden="true" /><h3>AI usage</h3><strong>{platformTokens.toLocaleString()}</strong><p>{money(platformCost)} model cost recorded.</p></article>
            <article className="metric-card"><Users size={22} color="var(--color-primary)" aria-hidden="true" /><h3>Members</h3><strong>{Number(platformTotals.members ?? 0).toLocaleString()}</strong><p>Active members across listed accounts.</p></article>
          </div>

          <div className="table-panel with-top-gap">
            <div className="table-header"><h2>Account sync status</h2><span className="status-badge neutral">{platformOverview?.accounts.length ?? 0} accounts</span></div>
            {platformOverview?.accounts.length ? (
              <table className="data-table">
                <thead><tr><th>Account</th><th>Credits</th><th>Tokens used</th><th>Cost</th><th>Members</th><th>Sync</th></tr></thead>
                <tbody>{platformOverview.accounts.map((account) => <tr key={account.id}><td><strong>{account.name}</strong><br /><span className="mono">{account.id}</span></td><td>{(account.credit_balance ?? account.credits).toLocaleString()}</td><td>{(account.tokens_used ?? 0).toLocaleString()}</td><td>{money(Number(account.usage_cost ?? 0))}</td><td>{account.team_size.toLocaleString()}</td><td>{account.sync_errors && Object.keys(account.sync_errors).length ? <span className="status-badge danger">Issue</span> : <span className="status-badge live">Synced</span>}</td></tr>)}</tbody>
              </table>
            ) : <div className="empty-state">{loading ? "Loading platform overview..." : "No platform account data loaded."}</div>}
          </div>
        </>
      ) : (
        <>
          <div className="metric-grid with-top-gap">
            <article className="metric-card"><Coins size={22} color="var(--color-primary)" aria-hidden="true" /><h3>Credit balance</h3><strong>{accountTotals.balance.toLocaleString()}</strong><p>Current visible balance.</p></article>
            <article className="metric-card"><Activity size={22} color="var(--color-primary)" aria-hidden="true" /><h3>Tokens used</h3><strong>{accountTotals.tokens.toLocaleString()}</strong><p>{money(accountTotals.cost)} model cost recorded.</p></article>
            <article className="metric-card"><Gauge size={22} color="var(--color-primary)" aria-hidden="true" /><h3>Usage ratio</h3><strong>{accountTotals.ratio}%</strong><p>Derived from quota and tokens when available.</p></article>
          </div>

          <div className="table-panel with-top-gap">
            <div className="table-header"><h2>Account summary</h2><span className="status-badge neutral">{overview ? "Live" : loading ? "Loading" : "No account loaded"}</span></div>
            {overview ? (
              <table className="data-table"><thead><tr><th>Account</th><th>Plan</th><th>Members</th><th>Credits service</th><th>Usage service</th></tr></thead><tbody><tr><td><strong>{stringFromRecord(overview.account, ["name"], overview.account_id)}</strong><br /><span className="mono">{overview.account_id}</span></td><td>{stringFromRecord(overview.account, ["plan", "tier"], "Unknown")}</td><td className="mono">{overview.members?.length ?? 0}</td><td><span className={overview.errors?.credits ? "status-badge danger" : "status-badge live"}>{overview.errors?.credits ? "Error" : "OK"}</span></td><td><span className={overview.errors?.usage ? "status-badge danger" : "status-badge live"}>{overview.errors?.usage ? "Error" : "OK"}</span></td></tr></tbody></table>
            ) : <div className="empty-state">{loading ? "Loading account overview..." : "No account loaded."}</div>}
          </div>
        </>
      )}
    </section>
  );
}
