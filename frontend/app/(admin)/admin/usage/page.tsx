import { Activity, Coins, Gauge } from "lucide-react";
import { adminAccounts } from "@/lib/mock-data";

export default function UsagePage() {
  const totalCredits = adminAccounts.reduce((sum, account) => sum + account.credits, 0);
  const totalUsage = adminAccounts.reduce((sum, account) => sum + account.usage, 0);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Global dashboard</h1>
          <p className="page-subtitle">Per-account usage and credit balances across the platform.</p>
        </div>
      </div>

      <div className="metric-grid">
        <article className="metric-card">
          <Coins size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Total credits</h3>
          <strong>{totalCredits.toLocaleString()}</strong>
          <p>Current balances across visible accounts.</p>
        </article>
        <article className="metric-card">
          <Activity size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credits used</h3>
          <strong>{totalUsage.toLocaleString()}</strong>
          <p>Month-to-date generation and publishing events.</p>
        </article>
        <article className="metric-card">
          <Gauge size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Average usage</h3>
          <strong>{Math.round(totalUsage / adminAccounts.length).toLocaleString()}</strong>
          <p>Average credits consumed per account.</p>
        </article>
      </div>

      <div className="table-panel">
        <div className="table-header">
          <h2>Accounts</h2>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Account</th>
              <th>Plan</th>
              <th>Balance</th>
              <th>Usage</th>
              <th>Usage ratio</th>
            </tr>
          </thead>
          <tbody>
            {adminAccounts.map((account) => {
              const ratio = Math.min(Math.round((account.usage / Math.max(account.credits, 1)) * 100), 100);
              return (
                <tr key={account.id}>
                  <td>{account.name}</td>
                  <td>{account.plan}</td>
                  <td className="mono">{account.credits.toLocaleString()}</td>
                  <td className="mono">{account.usage.toLocaleString()}</td>
                  <td>
                    <div className="progress-track" aria-label={`${ratio}%`}>
                      <div className="progress-fill" style={{ width: `${ratio}%` }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

