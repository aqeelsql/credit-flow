"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Search, Users } from "lucide-react";
import { adminFetch, numberFromRecord, stringFromRecord, type AdminAccountOverview, type AdminAuditResponse } from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

export default function DirectoryPage() {
  const { accessToken } = useAuth();
  const [query, setQuery] = useState("");
  const [discoveredAccounts, setDiscoveredAccounts] = useState<string[]>([]);
  const [overview, setOverview] = useState<AdminAccountOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDiscovered = async () => {
      try {
        const audit = await adminFetch<AdminAuditResponse>("/audit-log?limit=200", accessToken);
        const ids = Array.from(new Set((audit.items ?? []).map((item) => item.account_id).filter((id): id is string => !!id)));
        setDiscoveredAccounts(ids.slice(0, 20));
      } catch {
        setDiscoveredAccounts([]);
      }
    };
    void loadDiscovered();
  }, [accessToken]);

  const loadOverview = useCallback(
    async (accountId = query) => {
      const nextAccountId = accountId.trim();
      if (!nextAccountId) {
        setError("Enter an account_id to inspect.");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        setQuery(nextAccountId);
        setOverview(await adminFetch<AdminAccountOverview>(`/accounts/${encodeURIComponent(nextAccountId)}/overview`, accessToken));
      } catch (err) {
        setOverview(null);
        setError(err instanceof Error ? err.message : "Unable to load account overview.");
      } finally {
        setLoading(false);
      }
    },
    [accessToken, query]
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
          <h1 className="page-title">Account operations</h1>
          <p className="page-subtitle">Look up an account and aggregate plan, credits, usage, and member details through read-only service calls.</p>
        </div>
      </div>

      <div className="panel search-row">
        <div className="field">
          <label htmlFor="directory-search">Account ID</label>
          <input id="directory-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Paste account_id" />
        </div>
        <button className="button primary" type="button" onClick={() => void loadOverview()} disabled={loading}>
          <Search size={16} aria-hidden="true" />
          Inspect
        </button>
      </div>

      {discoveredAccounts.length ? (
        <div className="panel with-top-gap">
          <div className="panel-header">
            <h2>Accounts seen in audit trail</h2>
            <span className="status-badge neutral">{discoveredAccounts.length} discovered</span>
          </div>
          <div className="button-row compact">
            {discoveredAccounts.map((accountId) => (
              <button className="button ghost" type="button" key={accountId} onClick={() => void loadOverview(accountId)}>
                {accountId}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {error ? <div className="danger-note with-top-gap">{error}</div> : null}

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
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                  </tr>
                </thead>
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
