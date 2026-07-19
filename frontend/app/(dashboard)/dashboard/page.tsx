"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, Coins, Users, WalletCards, Zap } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";

type BalanceResponse = { balance: number; low_balance_threshold?: number; is_low_balance?: boolean };

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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    const load = async () => {
      setError(null);
      const response = await fetch("/api/credits/balance", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" });
      if (!response.ok) throw new Error(await readError(response));
      const data = (await response.json()) as BalanceResponse;
      setBalance(data.balance);
    };
    load().catch((err) => setError(err instanceof Error ? err.message : "Unable to load credit balance."));
  }, [accessToken]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Owner dashboard</h1>
          <p className="page-subtitle">Live account scope for {activeAccount?.name ?? "the active account"}.</p>
        </div>
        <span className="status-badge live">Real data</span>
      </div>

      {error ? <div className="danger-note">{error}</div> : null}

      <div className="metric-grid">
        <article className="metric-card">
          <Coins size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credit balance</h3>
          <strong>{(balance ?? activeAccount?.credits ?? 0).toLocaleString()}</strong>
          <p>Read from Credits Service.</p>
        </article>
        <article className="metric-card">
          <Zap size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credits used</h3>
          <strong>—</strong>
          <p>Usage Service data appears in the Admin/Ops dashboard.</p>
        </article>
        <article className="metric-card">
          <Users size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Team size</h3>
          <strong>{activeAccount?.teamSize ?? 0}</strong>
          <p>Current plan: {activeAccount?.plan ?? "Unknown"}.</p>
        </article>
      </div>

      <div className="admin-grid with-top-gap">
        <article className="panel">
          <div className="panel-header"><h2>Usage signal</h2><span className="status-badge neutral">Live only</span></div>
          <p>No generated placeholder activity is shown in staging. Events will appear after real service activity is recorded.</p>
        </article>
        <article className="panel">
          <div className="panel-header"><h2>Plan posture</h2><WalletCards size={22} color="var(--color-primary)" aria-hidden="true" /></div>
          <p>Use Credits and Billing to manage real balances and plan changes.</p>
          <div className="button-row with-top-gap"><a className="button secondary" href="/credits">Manage credits <ArrowUpRight size={15} aria-hidden="true" /></a></div>
        </article>
      </div>
    </section>
  );
}
