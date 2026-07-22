"use client";

import { useCallback, useEffect, useState } from "react";
import { CreditCard, Loader2, PackageCheck } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";

type Balance = { balance: number };
type CreditPackage = { key: string; credits: number; price_cents: number; currency: string };
type CreditCheckout = { checkout_url?: string | null; session_id?: string | null; package_key: string; status: string };
type CreditCheckoutSync = { status: string; credits: number; amount_paid: number; currency: string };

async function api<T>(path: string, token: string | null, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body?.message === "string" ? body.message : typeof body?.error === "string" ? body.error : response.statusText;
    throw new Error(message || "Request failed.");
  }
  return body as T;
}

function money(priceCents: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD" }).format(priceCents / 100);
}

export default function CreditsPage() {
  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <CreditsPurchase />
    </RouteGuard>
  );
}

function CreditsPurchase() {
  const { accessToken, activeAccount } = useAuth();
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [selectedCredits, setSelectedCredits] = useState<Record<string, number>>({});
  const [balance, setBalance] = useState<number | null>(null);
  const [busyPackage, setBusyPackage] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadCredits = useCallback(async () => {
    if (!accessToken) return;
    setError(null);
    try {
      const [balanceResponse, packageResponse] = await Promise.all([
        api<Balance>("/api/credits/balance", accessToken),
        api<CreditPackage[]>("/api/billing/credits/packages", accessToken)
      ]);
      setBalance(balanceResponse.balance);
      setPackages(packageResponse);
      setSelectedCredits((current) => {
        const next = { ...current };
        for (const item of packageResponse) {
          if (!next[item.key]) next[item.key] = item.credits;
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load credit packages.");
    }
  }, [accessToken]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const checkout = params.get("checkout");
    const sessionId = params.get("session_id");
    if (checkout === "cancelled") {
      setNotice("Credit checkout was cancelled. No payment was made.");
      void loadCredits();
      return;
    }
    if (checkout === "success" && sessionId && accessToken) {
      setNotice("Finalizing your credit purchase...");
      api<CreditCheckoutSync>(`/api/billing/checkout/credits/${encodeURIComponent(sessionId)}/sync`, accessToken, { method: "POST" })
        .then((result) => {
          setNotice(`Credit purchase synced. Added ${result.credits.toLocaleString()} credits to your account.`);
          window.history.replaceState(null, "", "/credits?checkout=success");
        })
        .catch((err) => setError(err instanceof Error ? err.message : "Unable to sync credit purchase."))
        .finally(() => void loadCredits());
      return;
    }
    if (checkout === "success") setNotice("Credit checkout completed. Refreshing your balance...");
    void loadCredits();
  }, [accessToken, loadCredits]);

  const unitPriceCents = (item: CreditPackage) => item.price_cents / item.credits;
  const selectedAmount = (item: CreditPackage) => Math.max(1, Math.floor(selectedCredits[item.key] || item.credits));
  const estimatedPrice = (item: CreditPackage) => Math.max(1, Math.round(selectedAmount(item) * unitPriceCents(item)));

  const buyPackage = async (item: CreditPackage) => {
    setError(null);
    setNotice("");
    setBusyPackage(item.key);
    try {
      const credits = selectedAmount(item);
      const checkout = await api<CreditCheckout>("/api/billing/checkout/credits", accessToken, {
        method: "POST",
        body: JSON.stringify({ package_key: item.key, credits })
      });
      if (!checkout.checkout_url) throw new Error("Unable to open the secure checkout page.");
      window.location.href = checkout.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start credit checkout.");
      setBusyPackage(null);
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Buy credits</h1>
          <p className="page-subtitle">Add credits to {activeAccount?.name ?? "the active account"} and keep your content workflow moving without interruption.</p>
        </div>
        <span className="status-badge live">Balance {(balance ?? 0).toLocaleString()}</span>
      </div>

      {notice ? <div className="notice">{notice}</div> : null}
      {error ? <div className="danger-note with-top-gap">{error}</div> : null}

      <div className="card-grid with-top-gap">
        {packages.length ? packages.map((item) => (
          <article className="feature-card credit-package-card" key={item.key}>
            <PackageCheck size={24} color="var(--color-primary)" aria-hidden="true" />
            <h3>{item.key}</h3>
            <p>
              {item.credits.toLocaleString()} credits available at {money(item.price_cents, item.currency)}.
            </p>
            <div className="field with-top-gap">
              <label htmlFor={`credits-${item.key}`}>Credits to buy</label>
              <input
                id={`credits-${item.key}`}
                type="number"
                min={1}
                step={100}
                value={selectedCredits[item.key] ?? item.credits}
                onChange={(event) =>
                  setSelectedCredits((current) => ({
                    ...current,
                    [item.key]: Number(event.target.value)
                  }))
                }
              />
            </div>
            <strong className="metric-value">{money(estimatedPrice(item), item.currency)}</strong>
            <div className="credit-package-actions with-top-gap"><button className="button primary compact" type="button" onClick={() => void buyPackage(item)} disabled={busyPackage !== null}>
              {busyPackage === item.key ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <CreditCard size={16} aria-hidden="true" />}
              {busyPackage === item.key ? "Opening checkout..." : `Buy ${selectedAmount(item).toLocaleString()} credits`}
            </button></div>
          </article>
        )) : <div className="empty-state">No credit packages are configured yet.</div>}
      </div>
    </section>
  );
}



