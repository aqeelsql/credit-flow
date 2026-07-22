"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, Coins, Users, WalletCards, Zap } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";

type BalanceResponse = { balance: number; low_balance_threshold?: number; is_low_balance?: boolean };
type CreditTransaction = { id: string; amount: number; reason: string; source_event_id?: string | null; metadata?: Record<string, unknown>; created_at: string };

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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    const load = async () => {
      setError(null);
      const response = await fetch("/api/credits/balance", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" });
      if (!response.ok) throw new Error(await readError(response));
      const data = (await response.json()) as BalanceResponse;
      setBalance(data.balance);
      const txResponse = await fetch("/api/credits/transactions?limit=10", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" });
      if (txResponse.ok) {
        const transactions = (await txResponse.json()) as CreditTransaction[];
        setPurchases(transactions.filter((item) => item.amount > 0 && item.reason === "purchase").slice(0, 5));
        setCreditsUsed(transactions.filter((item) => item.amount < 0).reduce((sum, item) => sum + Math.abs(item.amount), 0));
      }
    };
    load().catch((err) => setError(err instanceof Error ? err.message : "Unable to load credit balance."));
  }, [accessToken]);

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
          <h3>Credits used</h3>
          <strong>{creditsUsed.toLocaleString()}</strong>
          <p>Track usage across generated content.</p>
        </article>
        <article className="metric-card">
          <Users size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Team size</h3>
          <strong>{activeAccount?.teamSize ?? 0}</strong>
          <p>Current plan: {activeAccount?.plan ?? "Unknown"}.</p>
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









