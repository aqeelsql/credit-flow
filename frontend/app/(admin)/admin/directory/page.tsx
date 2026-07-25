"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, RefreshCw, Search, Users } from "lucide-react";
import {
  adminFetch,
  numberFromRecord,
  stringFromRecord,
  type AdminAccountDirectoryItem,
  type AdminAccountDirectoryResponse,
  type AdminAccountOverview
} from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

type DirectoryAccount = AdminAccountDirectoryItem & {
  credit_balance?: number | null;
  tokens_used?: number | null;
  sync_errors?: Record<string, string>;
};

type DirectoryResponse = DirectoryAccount[] | { items?: DirectoryAccount[]; errors?: Record<string, string> };

function normalizeDirectoryResponse(response: DirectoryResponse) {
  if (Array.isArray(response)) return { items: response, errors: {} as Record<string, string> };
  return { items: response.items ?? [], errors: response.errors ?? {} };
}

function compactId(value?: string | null, size = 14) {
  if (!value) return "—";
  return value.length > size + 4 ? `${value.slice(0, size)}…${value.slice(-4)}` : value;
}

function money(cents?: number | null, currency = "usd") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() }).format(Number(cents ?? 0) / 100);
}

export default function DirectoryPage() {
  const { accessToken } = useAuth();
  const [query, setQuery] = useState("");
  const [accounts, setAccounts] = useState<DirectoryAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [overview, setOverview] = useState<AdminAccountOverview | null>(null);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [directoryWarnings, setDirectoryWarnings] = useState<Record<string, string>>({});

  const loadAccounts = useCallback(async () => {
    setLoadingAccounts(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (query.trim()) params.set("q", query.trim());
      const response = await adminFetch<DirectoryResponse>(`/accounts?${params.toString()}`, accessToken);
      const normalized = normalizeDirectoryResponse(response);
      setAccounts(normalized.items);
      setDirectoryWarnings(normalized.errors);
      const first = normalized.items[0]?.id ?? "";
      if (!selectedAccountId && first) setSelectedAccountId(first);
    } catch (err) {
      setAccounts([]);
      setDirectoryWarnings({});
      setError(err instanceof Error ? err.message : "Unable to load account directory.");
    } finally {
      setLoadingAccounts(false);
    }
  }, [accessToken, query, selectedAccountId]);

  const loadOverview = useCallback(
    async (accountId: string) => {
      const nextAccountId = accountId.trim();
      if (!nextAccountId) return;
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
    [accessToken]
  );

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    if (!overview && selectedAccountId) void loadOverview(selectedAccountId);
  }, [loadOverview, overview, selectedAccountId]);

  const selectedAccount = useMemo(() => accounts.find((account) => account.id === selectedAccountId), [accounts, selectedAccountId]);
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
          <p className="page-subtitle">Browse accounts with current plan, credit, usage, and member information.</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void loadAccounts()} disabled={loadingAccounts}>
          <RefreshCw className={loadingAccounts ? "spin" : ""} size={16} aria-hidden="true" />
          Refresh
        </button>
      </div>

      <div className="panel search-row">
        <div className="field">
          <label htmlFor="directory-search">Search accounts</label>
          <input id="directory-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Account name, owner email, or account ID" />
        </div>
        <button className="button primary" type="button" onClick={() => void loadAccounts()} disabled={loadingAccounts}>
          <Search size={16} aria-hidden="true" />
          Search
        </button>
      </div>

      {error ? <div className="danger-note with-top-gap">{error}</div> : null}
      {Object.keys(directoryWarnings).length ? <div className="warning-note with-top-gap">Directory warnings: {Object.entries(directoryWarnings).map(([key, value]) => `${key}: ${value}`).join(" | ")}</div> : null}

      <div className="table-panel with-top-gap">
        <div className="table-header">
          <h2>Synced accounts</h2>
          <span className="status-badge neutral">{loadingAccounts ? "Loading" : `${accounts.length} accounts`}</span>
        </div>
        {accounts.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Owner</th>
                <th>Plan</th>
                <th>Credits</th>
                <th>AI usage</th>
                <th>Members</th>
                <th>Invoices</th>
                <th>Sync</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => {
                const rowErrors = account.sync_errors ?? {};
                return (
                  <tr key={account.id} className={account.id === selectedAccountId ? "selected-row" : undefined}>
                    <td>
                      <strong>{account.name}</strong>
                      <br />
                      <span className="muted mono">{compactId(account.id)}</span>
                    </td>
                    <td>
                      {account.owner_name || "No owner name"}
                      <br />
                      <span className="muted-text">{account.owner_email || "No owner email"}</span>
                    </td>
                    <td>
                      <strong>{account.subscription_plan ?? account.plan}</strong>
                      <br />
                      <span className="muted-text">{account.subscription_status ?? "No billing status"}</span>
                    </td>
                    <td className="mono">{(account.credit_balance ?? account.credits).toLocaleString()}</td>
                    <td className="mono">{(account.tokens_used ?? 0).toLocaleString()}</td>
                    <td className="mono">{account.team_size.toLocaleString()}</td>
                    <td>
                      <span className="mono">{Number(account.invoice_count ?? 0).toLocaleString()}</span>
                      <br />
                      <span className="muted-text">{money(account.subscription_revenue_cents ?? 0)}</span>
                    </td>
                    <td>{Object.keys(rowErrors).length ? <span className="status-badge warning">Partial</span> : <span className="status-badge live">Synced</span>}</td>
                    <td>
                      <button className="button ghost" type="button" onClick={() => void loadOverview(account.id)} disabled={loadingOverview && selectedAccountId === account.id}>
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">{loadingAccounts ? "Loading synced accounts..." : "No accounts found."}</div>
        )}
      </div>

      {selectedAccount || overview ? (
        <>
          <div className="metric-grid with-top-gap">
            <article className="metric-card">
              <h3>Plan</h3>
              <strong>{stringFromRecord(overview?.account, ["subscription_plan", "plan", "tier"], selectedAccount?.subscription_plan ?? selectedAccount?.plan ?? "Unknown")}</strong>
              <p>{stringFromRecord(overview?.account, ["name"], selectedAccount?.name ?? selectedAccountId)}</p>
            </article>
            <article className="metric-card">
              <h3>Credit balance</h3>
              <strong>{metrics.credits.toLocaleString()}</strong>
              <p>Current available balance.</p>
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
              <span className="status-badge neutral">{overview?.members?.length ?? selectedAccount?.team_size ?? 0} users</span>
            </div>
            {overview?.members?.length ? (
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
              <div className="empty-state"><Users size={22} aria-hidden="true" /> {loadingOverview ? "Loading members..." : "Select Inspect to load member details."}</div>
            )}
          </div>

          <div className="table-panel with-top-gap">
            <div className="table-header">
              <h2>Billing invoices</h2>
              <span className="status-badge neutral">{overview?.invoices?.length ?? selectedAccount?.invoice_count ?? 0} invoices</span>
            </div>
            {overview?.invoices?.length ? (
              <table className="data-table">
                <thead><tr><th>Invoice</th><th>Plan</th><th>Amount</th><th>Status</th><th>Date</th><th>Open</th><th>Download</th></tr></thead>
                <tbody>
                  {overview.invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td className="mono">{invoice.stripe_invoice_id ?? invoice.id}</td>
                      <td>{invoice.subscription_plan ?? (invoice.stripe_subscription_id ? "Subscription" : "Credit purchase")}</td>
                      <td className="mono">{money(invoice.amount_paid || invoice.amount_due, invoice.currency)}</td>
                      <td><span className="status-badge success">{invoice.status}</span></td>
                      <td className="mono">{new Date(invoice.created_at).toLocaleDateString()}</td>
                      <td>
                        {invoice.hosted_invoice_url ? (
                          <a className="icon-button ghost" href={invoice.hosted_invoice_url} target="_blank" rel="noreferrer" aria-label="Open invoice">
                            <ExternalLink size={16} aria-hidden="true" />
                          </a>
                        ) : (
                          <span className="muted-text">-</span>
                        )}
                      </td>
                      <td>
                        {invoice.invoice_pdf ? (
                          <a className="icon-button ghost" href={invoice.invoice_pdf} target="_blank" rel="noreferrer" download aria-label="Download invoice PDF">
                            <Download size={16} aria-hidden="true" />
                          </a>
                        ) : (
                          <span className="muted-text">-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty-state">{loadingOverview ? "Loading invoices..." : "No invoices recorded for this account."}</div>
            )}
          </div>

          {overview?.errors && Object.keys(overview.errors).length ? (
            <div className="warning-note with-top-gap">Some downstream services did not respond: {Object.entries(overview.errors).map(([key, value]) => `${key}: ${value}`).join(" | ")}</div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}


