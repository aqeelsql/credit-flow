"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Coins, DollarSign, Gauge, RefreshCw } from "lucide-react";
import {
  adminFetch,
  numberFromRecord,
  stringFromRecord,
  type AdminAccountDirectoryItem,
  type AdminAccountDirectoryResponse,
  type AdminAccountOverview,
  type AdminOpsSummary
} from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

type CreditPackage = { credits?: number; active?: boolean };
type CreditPurchase = { credits?: number; amount_paid?: number; currency?: string };

export default function UsagePage() {
  const { accessToken, activeAccount, session } = useAuth();
  const [accounts, setAccounts] = useState<AdminAccountDirectoryItem[]>([]);
  const [accountId, setAccountId] = useState(activeAccount?.id ?? "");
  const [overview, setOverview] = useState<AdminAccountOverview | null>(null);
  const [opsSummary, setOpsSummary] = useState<AdminOpsSummary | null>(null);
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

  const loadOpsSummary = useCallback(async () => {
    if (!isSuperAdmin) return;
    try {
      const summary = await adminFetch<AdminOpsSummary>("/ops-summary", accessToken);
      if (Number(summary.total_credits_generated ?? 0) > 0) {
        setOpsSummary(summary);
        return;
      }

      const [packages, purchases] = await Promise.all([
        fetch("/api/billing/admin/credits/packages", {
          headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
          cache: "no-store"
        }).then((response) => response.ok ? response.json() as Promise<CreditPackage[]> : []),
        fetch("/api/billing/admin/credits/purchases", {
          headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
          cache: "no-store"
        }).then((response) => response.ok ? response.json() as Promise<CreditPurchase[]> : [])
      ]);

      const totalCreditsGenerated = packages.reduce((sum, item) => sum + Number(item.credits ?? 0), 0);
      const totalCreditsSold = purchases.length ? purchases.reduce((sum, item) => sum + Number(item.credits ?? 0), 0) : Number(summary.total_credits_sold ?? 0);
      const totalMoneyGenerated = purchases.length ? purchases.reduce((sum, item) => sum + Number(item.amount_paid ?? 0), 0) : Number(summary.total_money_generated_cents ?? 0);
      const activePackageCredits = packages.filter((item) => item.active !== false).reduce((sum, item) => sum + Number(item.credits ?? 0), 0);
      setOpsSummary({
        ...summary,
        total_credits_generated: totalCreditsGenerated,
        package_count: packages.length,
        active_package_count: packages.filter((item) => item.active !== false).length,
        active_package_credits: activePackageCredits,
        total_credits_sold: totalCreditsSold,
        credits_left: Math.max(totalCreditsGenerated - totalCreditsSold, 0),
        total_money_generated_cents: totalMoneyGenerated,
        currency: purchases[0]?.currency || summary.currency || "usd",
        purchase_count: purchases.length || summary.purchase_count || 0
      });
    } catch {
      setOpsSummary(null);
    }
  }, [accessToken, isSuperAdmin]);

  useEffect(() => {
    if (!accountId && activeAccount?.id) setAccountId(activeAccount.id);
  }, [accountId, activeAccount?.id]);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    void loadOpsSummary();
  }, [loadOpsSummary]);

  const loadOverview = useCallback(async () => {
    const targetAccountId = (accountId || activeAccount?.id || "").trim();
    if (!targetAccountId) {
      setError(isSuperAdmin ? "Select an account to load usage." : "No active account selected.");
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
  }, [accessToken, accountId, activeAccount?.id, isSuperAdmin]);

  useEffect(() => {
    if (accountId || activeAccount?.id) void loadOverview();
  }, [accountId, activeAccount?.id, loadOverview]);

  const selectedAccount = accounts.find((account) => account.id === accountId);
  const generatedCredits = Number(opsSummary?.total_credits_generated ?? 0);
  const soldCredits = Number(opsSummary?.total_credits_sold ?? 0);
  const creditsLeft = Number(opsSummary?.credits_left ?? 0);
  const packageCount = Number(opsSummary?.package_count ?? 0);
  const purchaseCount = Number(opsSummary?.purchase_count ?? 0);
  const activePackageCredits = Number(opsSummary?.active_package_credits ?? 0);
  const accountCount = Number(opsSummary?.account_count ?? 0);
  const moneyGenerated = (Number(opsSummary?.total_money_generated_cents ?? 0) / 100).toLocaleString(undefined, {
    style: "currency",
    currency: (opsSummary?.currency || "usd").toUpperCase()
  });
  const totals = useMemo(() => {
    const balance = numberFromRecord(overview?.credits, ["balance", "credits", "available_credits", "remaining_credits"]);
    const quota = numberFromRecord(overview?.usage, ["quota_tokens", "quota", "monthly_quota", "limit"]);
    const tokens = numberFromRecord(overview?.usage, ["used_tokens", "tokens_used", "total_tokens", "used", "usage"]);
    const remainingTokens = numberFromRecord(overview?.usage, ["remaining_tokens"]);
    const cost = numberFromRecord(overview?.usage, ["total_cost", "cost", "period_cost"]);
    const ratio = quota > 0 ? Math.min(Math.round((tokens / quota) * 100), 100) : 0;
    return { balance, quota, tokens, remainingTokens, cost, ratio };
  }, [overview]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Ops dashboard</h1>
          <p className="page-subtitle">Monitor platform credit inventory, revenue, account balances, usage, and members.</p>
        </div>
      </div>

      {isSuperAdmin ? (
        <div className="metric-grid with-top-gap">
          <article className="metric-card">
            <Coins size={22} color="var(--color-primary)" aria-hidden="true" />
            <h3>Generated credits</h3>
            <strong>{generatedCredits.toLocaleString()}</strong>
            <p>Credit package inventory</p>
          </article>
          <article className="metric-card">
            <Activity size={22} color="var(--color-primary)" aria-hidden="true" />
            <h3>Credits sold</h3>
            <strong>{soldCredits.toLocaleString()}</strong>
            <p>{purchaseCount.toLocaleString()} purchases</p>
          </article>
          <article className="metric-card">
            <Gauge size={22} color="var(--color-primary)" aria-hidden="true" />
            <h3>Credits left</h3>
            <strong>{creditsLeft.toLocaleString()}</strong>
            <p>Available package credits</p>
          </article>
          <article className="metric-card">
            <DollarSign size={22} color="var(--color-primary)" aria-hidden="true" />
            <h3>Money generated</h3>
            <strong>{moneyGenerated}</strong>
            <p>{accountCount.toLocaleString()} accounts</p>
          </article>
        </div>
      ) : null}

      <div className="panel search-row with-top-gap">
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
        <button className="button secondary" type="button" onClick={() => { void loadOverview(); void loadOpsSummary(); }} disabled={loading || !accountId}>
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
          <p>Account credit balance</p>
        </article>
        <article className="metric-card">
          <Activity size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Tokens used</h3>
          <strong>{totals.tokens.toLocaleString()}</strong>
          <p>{totals.quota ? `${totals.remainingTokens.toLocaleString()} tokens remaining` : `$${totals.cost.toFixed(4)} model cost`}</p>
        </article>
        <article className="metric-card">
          <Gauge size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Usage ratio</h3>
          <strong>{totals.ratio}%</strong>
          <p>{totals.quota ? `${totals.tokens.toLocaleString()} / ${totals.quota.toLocaleString()} tokens` : "No quota data"}</p>
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











