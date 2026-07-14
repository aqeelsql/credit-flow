"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { adminAccounts } from "@/lib/mock-data";

export default function DirectoryPage() {
  const [query, setQuery] = useState("");
  const filteredAccounts = useMemo(() => {
    const normalized = query.toLowerCase();
    return adminAccounts.filter(
      (account) =>
        account.name.toLowerCase().includes(normalized) ||
        account.owner.toLowerCase().includes(normalized) ||
        account.id.toLowerCase().includes(normalized)
    );
  }, [query]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Cross-account directory</h1>
          <p className="page-subtitle">Search all accounts across the platform.</p>
        </div>
      </div>

      <div className="panel search-row">
        <div className="field">
          <label htmlFor="directory-search">Search</label>
          <input
            id="directory-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Account, owner, or account_id"
          />
        </div>
        <Search size={22} color="var(--color-primary)" aria-hidden="true" />
      </div>

      <div className="table-panel">
        <div className="table-header">
          <h2>Accounts</h2>
          <span className="status-badge neutral">{filteredAccounts.length} results</span>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Account</th>
              <th>Owner</th>
              <th>Type</th>
              <th>Plan</th>
              <th>Credits</th>
            </tr>
          </thead>
          <tbody>
            {filteredAccounts.map((account) => (
              <tr key={account.id}>
                <td>
                  <strong>{account.name}</strong>
                  <br />
                  <span className="mono">{account.id}</span>
                </td>
                <td>{account.owner}</td>
                <td>{account.type}</td>
                <td>{account.plan}</td>
                <td className="mono">{account.credits.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
