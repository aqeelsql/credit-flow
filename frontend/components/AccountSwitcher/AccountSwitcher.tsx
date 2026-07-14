"use client";

import { Building2, ChevronsUpDown } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export function AccountSwitcher() {
  const { accounts, activeAccount, switchAccount, session } = useAuth();

  if (session?.role === "SuperAdmin") {
    return (
      <div className="account-switcher">
        <label>Scope</label>
        <div className="account-select-wrap">
          <select value="platform" disabled aria-label="Current platform scope">
            <option>CreditFlow Platform</option>
          </select>
          <Building2 size={17} aria-hidden="true" />
        </div>
      </div>
    );
  }

  return (
    <div className="account-switcher">
      <label htmlFor="account-switcher">Active account</label>
      <div className="account-select-wrap">
        <select
          id="account-switcher"
          value={activeAccount?.id ?? ""}
          onChange={(event) => void switchAccount(event.target.value)}
          aria-label="Switch active account"
          disabled={accounts.length === 0}
        >
          {accounts.length === 0 ? <option value="">No accounts yet</option> : null}
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name} - {account.role}
            </option>
          ))}
        </select>
        <ChevronsUpDown size={17} aria-hidden="true" />
      </div>
    </div>
  );
}
