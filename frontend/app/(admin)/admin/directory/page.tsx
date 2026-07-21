"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Search, Users } from "lucide-react";
import { adminFetch, compactId, numberFromRecord, stringFromRecord, type AdminAccountOverview, type AdminAccountRow } from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

export default function DirectoryPage() {
  const { accessToken } = useAuth();
  const [query, setQuery] = useState("");
  const [accounts, setAccounts] = useState<AdminAccountRow[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [overview, setOverview] = useState<AdminAccountOverview | null>(null);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAccounts = useCallback(async () => {
    setLoadingAccounts(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (query.trim()) params.set("q", query.trim());
      const rows = await adminFetch<AdminAccountRow[]>(`/accounts?${params.toString()}`, accessToken);
      setAccounts(rows);
      if (!selectedAccountId && rows[0]?.id) setSelectedAccountId(rows[0].id);
    } catch (err) {
      setAccounts([]);
      setError(err instanceof Error ? err.message : "Unable to load platform accounts.");
    } finally {
      setLoadingAccounts(false);
    }
  }, [accessToken, query, selectedAccountId]);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  const loadOverview = useCallback(
    async (accountId = selectedAccountId) => {
      const nextAccountId = accountId.trim();
      if (!nextAccountId) {
        setError("Select an account to inspect.");
        return;
      }
      setLoadingOverview(true);
      setError(null);
      try {
        setSelectedAccountId(nextAccountId);
        setOverview(await adminFetch<AdminAccountOverview>(`/accounts/${encodeURIComponent(nextAccountId)}/overview`, accessToken));
      } catch (err) {
        setOverview(null);
        setError(err instanceof Error ? err.message : "Unable to load account overview.");
      } finally {
        setLoadingOverview(false);
      }
    },
    [accessToken, selectedAccountId]
  );

  const metrics = useMemo(() => {
    const credits = numberFromRecord(overview?.credits, ["balance", "credits", "available_credits", "remaining_credits"]);
    const usage = numberFromRecord(overview?.usage, ["tokens_used", "total_tokens", "used", "usage"]);
    const cost = numberFromRecord(overview?.usage, ["total_cost", "cost", "period_cost"]);
    return { credits, usage, cost };
  }, [overview]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Cross-account directory</h1>
          <p className="page-subtitle">Browse every registered account and inspect plan, credits, usage, and active members.</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void loadAccounts()} disabled={loadingAccounts}>
          <RefreshCw size={15} aria-hidden="true" />
          Refresh
        </button>
      </div>

      <div className="panel search-row">
        <div className="field">
          <label htmlFor="directory-search">Search accounts</label>
          <input id="directory-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Account name, owner email, or account_id" />
        </div>
        <button className="button primary" type="button" onClick={() => void loadAccounts()} disabled={loadingAccounts}>
          <Search size={16} aria-hidden="true" />
          Search
        </button>
      </div>

      {error ? <div className="danger-note with-top-gap">{error}</div> : null}

      <div className="table-panel with-top-gap">
        <div className="table-header">
          <h2>Registered accounts</h2>
          <span className="status-badge neutral">{loadingAccounts ? "Loading" : `${accounts.length} shown`}</span>
        </div>
        {accounts.length ? (
          <table className="data-table">
            <thead><tr><th>Account</th><th>Owner</th><th>Plan</th><th>Credits</th><th>AI usage</th><th>Members</th><th>Sync</th><th>Action</th></tr></thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td><strong>{account.name}</strong><br /><span className="muted mono">{compactId(account.id, 14)}</span></td>
                  <td>{account.owner_email ?? "Unknown"}</td>
                  <td>{account.plan}</td>
                  <td>{(account.credit_balance ?? account.credits).toLocaleString()}</td>
                  <td>{account.team_size.toLocaleString()}</td>
                  <td>{account.created_at ? new Date(account.created_at).toLocaleString() : "Unknown"}</td>
                  <td><button className="button ghost" type="button" onClick={() => void loadOverview(account.id)} disabled={loadingOverview}>Inspect</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">{loadingAccounts ? "Loading registered accounts..." : "No accounts found."}</div>
        )}
      </div>

      {overview ? (
        <>
          <div className="metric-grid with-top-gap">
            <article className="metric-card">
              <h3>Plan</h3>
              <strong>{stringFromRecord(overview.account, ["plan", "tier"], "Unknown")}</strong>
              <p>{stringFromRecord(overview.account, ["name"], overview.account_id)}</p>
            </article>
            <article className="metric-card">
              <h3>Credit balance</h3>
              <strong>{metrics.credits.toLocaleString()}</strong>
              <p>Read from Credits service.</p>
            </article>
            <article className="metric-card">
              <h3>Usage / cost</h3>
              <strong>{metrics.usage.toLocaleString()}</strong>
              <p>${metrics.cost.toFixed(4)} this period.</p>
            </article>
          </div>

          <div className="table-panel with-top-gap">
            <div className="table-header">
              <h2>Active members</h2>
              <span className="status-badge neutral">{overview.members?.length ?? 0} users</span>
            </div>
            {overview.members?.length ? (
              <table className="data-table">
                <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
                <tbody>
                  {overview.members.map((member, index) => (
                    <tr key={String(member.id ?? member.user_id ?? index)}>
                      <td>{stringFromRecord(member, ["name", "user_id", "id"])}</td>
                      <td>{stringFromRecord(member, ["email"])}</td>
                      <td>{stringFromRecord(member, ["role"])}</td>
                      <td><span className="status-badge live">{stringFromRecord(member, ["status"], "Active")}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state"><Users size={22} aria-hidden="true" /> No member data returned for this account.</div>
            )}
          </div>

          {overview.errors && Object.keys(overview.errors).length ? (
            <div className="warning-note with-top-gap">Some downstream services did not respond: {Object.entries(overview.errors).map(([key, value]) => `${key}: ${value}`).join(" | ")}</div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

