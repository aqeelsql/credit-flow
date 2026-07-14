"use client";

import { ArrowUpRight, Coins, Users, WalletCards, Zap } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";
import { dashboardSummary } from "@/lib/mock-data";

export default function DashboardPage() {
  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <OwnerDashboard />
    </RouteGuard>
  );
}

function OwnerDashboard() {
  const { activeAccount } = useAuth();

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Owner dashboard</h1>
          <p className="page-subtitle">
            Account-wide usage, balance, team size, and plan for {activeAccount?.name ?? "the active account"}.
          </p>
        </div>
        <span className="status-badge live">Live account scope</span>
      </div>

      <div className="metric-grid">
        <article className="metric-card">
          <Coins size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credit balance</h3>
          <strong>{(activeAccount?.credits ?? dashboardSummary.creditBalance).toLocaleString()}</strong>
          <p>Available for AI generation, scheduling, and image actions.</p>
        </article>
        <article className="metric-card">
          <Zap size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credits used</h3>
          <strong>{dashboardSummary.creditsUsed.toLocaleString()}</strong>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${dashboardSummary.usagePercent}%` }} />
          </div>
          <p>{dashboardSummary.usagePercent}% of current monthly plan allocation.</p>
        </article>
        <article className="metric-card">
          <Users size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Team size</h3>
          <strong>{activeAccount?.teamSize ?? dashboardSummary.teamSize}</strong>
          <p>Current plan: {activeAccount?.plan ?? dashboardSummary.currentPlan}.</p>
        </article>
      </div>

      <div className="admin-grid with-top-gap">
        <article className="panel">
          <div className="panel-header">
            <h2>Usage signal</h2>
            <span className="status-badge live">Now</span>
          </div>
          <p>
            Content Studio generated {dashboardSummary.contentGenerated} drafts this cycle. Low-friction drafts are
            converting into scheduled LinkedIn posts at a stable pace.
          </p>
        </article>
        <article className="panel">
          <div className="panel-header">
            <h2>Plan posture</h2>
            <WalletCards size={22} color="var(--color-primary)" aria-hidden="true" />
          </div>
          <p>
            The active plan has enough credits for the next two publishing waves. Marketplace buying is available from
            Credits when usage spikes.
          </p>
          <div className="button-row with-top-gap">
            <a className="button secondary" href="/credits">
              Manage credits
              <ArrowUpRight size={15} aria-hidden="true" />
            </a>
          </div>
        </article>
      </div>
    </section>
  );
}
