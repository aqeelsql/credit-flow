"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Coins, Users, WalletCards, Zap } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";

type BalanceResponse = { balance: number; low_balance_threshold?: number; is_low_balance?: boolean };
type CreditTransaction = { id: string; amount: number; reason: string; source_event_id?: string | null; metadata?: Record<string, unknown>; created_at: string };
type UsageSummary = { used_tokens: number };
type TeamRow = { id: string; role: string; status: string };
type SubscriptionProfile = { plan: string; status: string; current_period_end?: string | null };

async function readError(response: Response) {
  try {
    const body = (await response.json()) as { error?: string | { message?: string }; message?: string };
    return body.message || (typeof body.error === "string" ? body.error : body.error?.message) || response.statusText;
  } catch {
    return response.statusText;
  }
}

export default function DashboardPage() {
  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <OwnerDashboard />
    </RouteGuard>
  );
}

function OwnerDashboard() {
  const { activeAccount, accessToken } = useAuth();
  const [balance, setBalance] = useState<number | null>(null);
  const [purchases, setPurchases] = useState<CreditTransaction[]>([]);
  const [creditsUsed, setCreditsUsed] = useState(0);
  const [subscription, setSubscription] = useState<SubscriptionProfile | null>(null);
  const [teamMemberCount, setTeamMemberCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    const load = async () => {
      setError(null);
      const response = await fetch("/api/credits/balance", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" });
      if (!response.ok) throw new Error(await readError(response));
      const data = (await response.json()) as BalanceResponse;
      setBalance(data.balance);
      const [txResponse, usageResponse, subscriptionResponse, teamResponse] = await Promise.all([
        fetch("/api/credits/transactions?limit=10", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }),
        activeAccount?.id ? fetch(`/api/usage/usage/accounts/${encodeURIComponent(activeAccount.id)}/summary`, { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }) : Promise.resolve(null),
        fetch("/api/billing/billing/subscription", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }),
        activeAccount?.id ? fetch(`/api/accounts/${encodeURIComponent(activeAccount.id)}/team`, { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }) : Promise.resolve(null)
      ]);
      if (txResponse.ok) {
        const transactions = (await txResponse.json()) as CreditTransaction[];
        setPurchases(transactions.filter((item) => item.amount > 0 && item.reason === "purchase").slice(0, 5));
      }
      if (usageResponse && usageResponse.ok) {
        const usage = (await usageResponse.json()) as UsageSummary;
        setCreditsUsed(Number(usage.used_tokens ?? 0));
      }
      if (subscriptionResponse.ok) {
        setSubscription((await subscriptionResponse.json()) as SubscriptionProfile);
      }
      if (teamResponse && teamResponse.ok) {
        const rows = (await teamResponse.json()) as TeamRow[];
        setTeamMemberCount(rows.filter((member) => member.status.toLowerCase() === "active" && member.role !== "Owner").length);
      }
    };
    load().catch((err) => setError(err instanceof Error ? err.message : "Unable to load credit balance."));
  }, [accessToken, activeAccount?.id]);

  const displayedTeamMembers = useMemo(() => {
    if (teamMemberCount !== null) return teamMemberCount;
    return Math.max((activeAccount?.teamSize ?? 1) - 1, 0);
  }, [activeAccount?.teamSize, teamMemberCount]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Owner dashboard</h1>
          <p className="page-subtitle">Account overview for {activeAccount?.name ?? "the active account"}.</p>
        </div>
        <span className="status-badge live">Real data</span>
      </div>

      {error ? <div className="danger-note">{error}</div> : null}

      <div className="metric-grid">
        <article className="metric-card">
          <Coins size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credit balance</h3>
          <strong>{(balance ?? activeAccount?.credits ?? 0).toLocaleString()}</strong>
          <p>Available balance for content generation.</p>
        </article>
        <article className="metric-card">
          <Zap size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>AI tokens used</h3>
          <strong>{creditsUsed.toLocaleString()}</strong>
          <p>credits used for content generation.</p>
        </article>
        <article className="metric-card">
          <Users size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Team size</h3>
          <strong>{displayedTeamMembers.toLocaleString()}</strong>
          <p>Current plan: {subscription?.plan ?? activeAccount?.plan ?? "Free"}.</p>
        </article>
      </div>

      <div className="admin-grid dashboard-panels with-top-gap">
        <article className="panel">
          <div className="panel-header"><h2>Recent credit purchases</h2><span className="status-badge neutral">{purchases.length} shown</span></div>
          {purchases.length ? (
            <table className="data-table">
              <thead><tr><th>Credits</th><th>Package</th><th>Date</th></tr></thead>
              <tbody>{purchases.map((item) => <tr key={item.id}><td className="mono">+{item.amount.toLocaleString()}</td><td>{String(item.metadata?.package_key ?? "Stripe checkout")}</td><td>{new Date(item.created_at).toLocaleString()}</td></tr>)}</tbody>
            </table>
          ) : <p>No credit purchases recorded yet.</p>}
        </article>
        <article className="panel">
          <div className="panel-header"><h2>Plan posture</h2><WalletCards size={22} color="var(--color-primary)" aria-hidden="true" /></div>
          <p>Manage credits, payment details, and account plan changes from one place.</p>
          <div className="button-row with-top-gap"><a className="button secondary" href="/credits">Manage credits <ArrowUpRight size={15} aria-hidden="true" /></a></div>
        </article>
      </div>
    </section>
  );
}









