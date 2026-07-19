"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Coins, Gauge, RefreshCw } from "lucide-react";
import { adminFetch, numberFromRecord, stringFromRecord, type AdminAccountOverview } from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

export default function UsagePage() {
  const { accessToken, activeAccount, session } = useAuth();
  const [accountId, setAccountId] = useState(activeAccount?.id ?? "");
  const [overview, setOverview] = useState<AdminAccountOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accountId && activeAccount?.id) setAccountId(activeAccount.id);
  }, [accountId, activeAccount?.id]);

  const loadOverview = useCallback(async () => {
    const targetAccountId = (accountId || activeAccount?.id || "").trim();
    if (!targetAccountId) {
      setError(session?.role === "SuperAdmin" ? "Enter an account_id to load usage." : "No active account selected.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setOverview(await adminFetch<AdminAccountOverview>(`/accounts/${encodeURIComponent(targetAccountId)}/overview`, accessToken));
    } catch (err) {
      setOverview(null);
      setError(err instanceof Error ? err.message : "Unable to load account usage.");
    } finally {
      setLoading(false);
    }
  }, [accessToken, accountId, activeAccount?.id, session?.role]);

  useEffect(() => {
    if (activeAccount?.id) void loadOverview();
  }, [activeAccount?.id, loadOverview]);

  const totals = useMemo(() => {
    const balance = numberFromRecord(overview?.credits, ["balance", "credits", "available_credits", "remaining_credits"]);
    const quota = numberFromRecord(overview?.credits, ["quota", "monthly_quota", "limit", "credits"]);
    const tokens = numberFromRecord(overview?.usage, ["tokens_used", "total_tokens", "used", "usage"]);
    const cost = numberFromRecord(overview?.usage, ["total_cost", "cost", "period_cost"]);
    const ratio = quota > 0 ? Math.min(Math.round(((quota - balance) / quota) * 100), 100) : 0;
    return { balance, quota, tokens, cost, ratio };
  }, [overview]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Ops dashboard</h1>
          <p className="page-subtitle">Per-account operational view: plan tier, credits, usage, and service aggregation health.</p>
        </div>
      </div>

      <div className="panel search-row">
        <div className="field">
          <label htmlFor="ops-account">Account ID</label>
          <input id="ops-account" value={accountId} onChange={(event) => setAccountId(event.target.value)} placeholder="Account to inspect" disabled={session?.role !== "SuperAdmin" && !!activeAccount?.id} />
        </div>
        <button className="button secondary" type="button" onClick={() => void loadOverview()} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={16} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error ? <div className="danger-note with-top-gap">{error}</div> : null}

      <div className="metric-grid with-top-gap">
        <article className="metric-card">
          <Coins size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credit balance</h3>
          <strong>{totals.balance.toLocaleString()}</strong>
          <p>{totals.quota ? `${totals.quota.toLocaleString()} quota` : "Current visible balance."}</p>
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
                  <strong>{stringFromRecord(overview.account, ["name"], overview.account_id)}</strong>
                  <br />
                  <span className="mono">{overview.account_id}</span>
                </td>
                <td>{stringFromRecord(overview.account, ["plan", "tier"], "Unknown")}</td>
                <td className="mono">{overview.members?.length ?? 0}</td>
                <td><span className={overview.errors?.credits ? "status-badge danger" : "status-badge live"}>{overview.errors?.credits ? "Error" : "OK"}</span></td>
                <td><span className={overview.errors?.usage ? "status-badge danger" : "status-badge live"}>{overview.errors?.usage ? "Error" : "OK"}</span></td>
              </tr>
            </tbody>
          </table>
        ) : (
          <div className="empty-state">{loading ? "Loading account overview…" : "Enter an account_id and refresh."}</div>
        )}
      </div>
    </section>
  );
}
