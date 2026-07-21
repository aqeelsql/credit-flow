"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, PackagePlus, RefreshCw, Trash2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

type CreditPackage = {
  id: string;
  key: string;
  credits: number;
  price_cents: number;
  currency: string;
  active: boolean;
};

type CreditPurchase = {
  id: string;
  account_id?: string | null;
  package_key?: string | null;
  credits: number;
  amount_paid: number;
  currency: string;
  stripe_checkout_session_id?: string | null;
  payment_intent_id?: string | null;
  published: boolean;
  created_at: string;
};

async function api<T>(path: string, token: string | null, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body?.error?.message === "string" ? body.error.message : typeof body?.message === "string" ? body.message : response.statusText;
    throw new Error(message || "Request failed.");
  }
  return body as T;
}

function money(priceCents: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD" }).format(priceCents / 100);
}

function keyFromCredits(credits: number) {
  return `credits_${credits}`.replace(/[^a-z0-9_-]/gi, "_").toLowerCase();
}

export default function AdminCreditPackagesPage() {
  const { accessToken } = useAuth();
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [purchases, setPurchases] = useState<CreditPurchase[]>([]);
  const [credits, setCredits] = useState(5000);
  const [price, setPrice] = useState("19.00");
  const [currency, setCurrency] = useState("usd");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const packageKey = useMemo(() => keyFromCredits(credits), [credits]);

  const loadPackages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [packageRows, purchaseRows] = await Promise.all([
        api<CreditPackage[]>("/api/billing/admin/credits/packages", accessToken),
        api<CreditPurchase[]>("/api/billing/admin/credits/purchases", accessToken)
      ]);
      setPackages(packageRows);
      setPurchases(purchaseRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load credit packages.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => { void loadPackages(); }, [loadPackages]);

  const createPackage = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice("");
    try {
      await api<CreditPackage>("/api/billing/admin/credits/packages", accessToken, {
        method: "POST",
        body: JSON.stringify({ key: packageKey, credits, price_cents: Math.round(Number(price) * 100), currency })
      });
      setNotice("Credit package created. Owners can now buy it from Credits.");
      await loadPackages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create package.");
    } finally {
      setSaving(false);
    }
  };

  const deactivatePackage = async (item: CreditPackage) => {
    setError(null);
    setNotice("");
    try {
      await api<CreditPackage>(`/api/billing/admin/credits/packages/${item.id}`, accessToken, { method: "DELETE" });
      setNotice("Credit package deactivated.");
      await loadPackages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to deactivate package.");
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Credit packages</h1>
          <p className="page-subtitle">Create credit amounts and prices that Owners can purchase through Billing and Stripe Checkout.</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void loadPackages()} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={16} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {notice ? <div className="notice">{notice}</div> : null}
      {error ? <div className="danger-note with-top-gap">{error}</div> : null}

      <form className="panel form-grid with-top-gap" onSubmit={createPackage}>
        <PackagePlus size={22} color="var(--color-primary)" aria-hidden="true" />
        <h2>Add package</h2>
        <div className="split-layout compact">
          <div className="field">
            <label htmlFor="package-credits">Credits</label>
            <input id="package-credits" type="number" min={1} step={100} value={credits} onChange={(event) => setCredits(Number(event.target.value))} required />
          </div>
          <div className="field">
            <label htmlFor="package-price">Price</label>
            <input id="package-price" inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="package-currency">Currency</label>
            <input id="package-currency" value={currency} onChange={(event) => setCurrency(event.target.value.toLowerCase())} required />
          </div>
        </div>
        <p className="muted-text">Generated key: <span className="mono">{packageKey}</span></p>
        <button className="button primary" type="submit" disabled={saving}>
          {saving ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <PackagePlus size={16} aria-hidden="true" />}
          {saving ? "Saving..." : "Create package"}
        </button>
      </form>

      <div className="table-panel with-top-gap">
        <div className="table-header"><h2>Packages</h2><span className="status-badge neutral">{packages.length} total</span></div>
        {packages.length ? (
          <table className="data-table">
            <thead><tr><th>Key</th><th>Credits</th><th>Price</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>
              {packages.map((item) => (
                <tr key={item.id}>
                  <td className="mono">{item.key}</td>
                  <td className="mono">{item.credits.toLocaleString()}</td>
                  <td className="mono">{money(item.price_cents, item.currency)}</td>
                  <td><span className={item.active ? "status-badge live" : "status-badge neutral"}>{item.active ? "Active" : "Inactive"}</span></td>
                  <td><button className="icon-button danger" type="button" onClick={() => void deactivatePackage(item)} disabled={!item.active} aria-label={`Deactivate ${item.key}`}><Trash2 size={16} aria-hidden="true" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state">No packages yet. Create the first package above.</div>}
      </div>

      <div className="table-panel with-top-gap">
        <div className="table-header"><h2>Owner credit purchases</h2><span className="status-badge neutral">{purchases.length} recent</span></div>
        {purchases.length ? (
          <table className="data-table">
            <thead><tr><th>Account</th><th>Package</th><th>Credits</th><th>Paid</th><th>Event</th><th>Date</th></tr></thead>
            <tbody>
              {purchases.map((item) => (
                <tr key={item.id}>
                  <td className="mono">{item.account_id || "—"}</td>
                  <td>{item.package_key || "Custom"}</td>
                  <td className="mono">+{item.credits.toLocaleString()}</td>
                  <td className="mono">{money(item.amount_paid, item.currency)}</td>
                  <td><span className={item.published ? "status-badge live" : "status-badge neutral"}>{item.published ? "Published" : "Queued"}</span></td>
                  <td>{new Date(item.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state">No owner credit purchases yet. Stripe payments will appear here after checkout completion.</div>}
      </div>
    </section>
  );
}
