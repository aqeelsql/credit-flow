"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, CreditCard, Download, Loader2, RefreshCcw } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";

type PlanKey = "free" | "starter" | "pro" | "team";

type CheckoutResponse = {
  checkout_url?: string | null;
  session_id?: string | null;
  plan: PlanKey;
  status: string;
};

type Invoice = {
  id: string;
  stripe_invoice_id?: string | null;
  amount_paid: number;
  amount_due: number;
  currency: string;
  status: string;
  hosted_invoice_url?: string | null;
  invoice_pdf?: string | null;
  created_at: string;
};

type SavedPaymentMethod = {
  stripe_payment_method_id: string;
  brand?: string | null;
  last4?: string | null;
  exp_month?: number | null;
  exp_year?: number | null;
};

const plans: Array<{ key: PlanKey; name: string; price: string; credits: string; detail: string; cta: string }> = [
  { key: "free", name: "Free", price: "$0", credits: "Limited credits", detail: "Use the product without a paid subscription or stored payment method.", cta: "Use Free" },
  { key: "starter", name: "Starter", price: "$29", credits: "4,000 credits", detail: "For solo operators testing an AI-assisted publishing workflow.", cta: "Pay Starter" },
  { key: "pro", name: "Pro", price: "$149", credits: "25,000 credits", detail: "For owners managing regular content generation and scheduling.", cta: "Pay Pro" },
  { key: "team", name: "Team", price: "$399", credits: "90,000 credits", detail: "For teams with approvals, publishing, and admin oversight.", cta: "Pay Team" }
];

function money(cents: number, currency: string) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD" }).format((cents || 0) / 100);
}

function readError(body: unknown, fallback: string) {
  if (body && typeof body === "object") {
    const value = body as { error?: string | { message?: string }; message?: string };
    if (typeof value.message === "string") return value.message;
    if (typeof value.error === "string") return value.error;
    if (value.error?.message) return value.error.message;
  }
  return fallback;
}

export default function BillingPage() {
  const { accessToken, activeAccount } = useAuth();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loadingInvoices, setLoadingInvoices] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<SavedPaymentMethod | null>(null);
  const [loadingPaymentMethod, setLoadingPaymentMethod] = useState(false);
  const [busyPlan, setBusyPlan] = useState<PlanKey | null>(null);
  const [savingCard, setSavingCard] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const queryNotice = useMemo(() => {
    if (typeof window === "undefined") return null;
    const searchParams = new URLSearchParams(window.location.search);
    const checkout = searchParams.get("checkout");
    const paymentMethodStatus = searchParams.get("payment_method");
    if (checkout === "success") return "Payment completed. Your invoice will appear shortly.";
    if (checkout === "cancelled") return "Checkout was cancelled. No payment was made.";
    if (paymentMethodStatus === "success") return "Payment method saved. Refreshing card details.";
    if (paymentMethodStatus === "cancelled") return "Payment method setup was cancelled. No card was saved.";
    return null;
  }, []);

  const authHeaders = () => ({ Authorization: `Bearer ${accessToken}` });

  async function loadInvoices() {
    if (!accessToken) return;
    setLoadingInvoices(true);
    setError(null);
    try {
      const response = await fetch("/api/billing/billing/invoices", { headers: authHeaders(), cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(readError(body, `Invoice history failed (${response.status}).`));
      setInvoices(Array.isArray(body.items) ? body.items : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invoice history failed to load.");
    } finally {
      setLoadingInvoices(false);
    }
  }

  async function loadPaymentMethod() {
    if (!accessToken) return;
    setLoadingPaymentMethod(true);
    setError(null);
    try {
      const response = await fetch("/api/billing/billing/payment-method", { headers: authHeaders(), cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(readError(body, `Payment method failed to load (${response.status}).`));
      setPaymentMethod(body.payment_method ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment method failed to load.");
    } finally {
      setLoadingPaymentMethod(false);
    }
  }

  async function savePaymentMethod() {
    if (!accessToken) return;
    setSavingCard(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch("/api/billing/billing/payment-method/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() }
      });
      const body = (await response.json().catch(() => ({}))) as { checkout_url?: string; error?: unknown; message?: string };
      if (!response.ok) throw new Error(readError(body, `Payment method setup failed (${response.status}).`));
      if (!body.checkout_url) throw new Error("Unable to open the secure card setup page.");
      window.location.href = body.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment method setup failed.");
    } finally {
      setSavingCard(false);
    }
  }

  async function startCheckout(plan: PlanKey) {
    if (!accessToken) return;
    setBusyPlan(plan);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch("/api/billing/checkout/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ plan })
      });
      const body = (await response.json().catch(() => ({}))) as CheckoutResponse & { error?: unknown; message?: string };
      if (!response.ok) throw new Error(readError(body, `Checkout session failed (${response.status}).`));

      if (body.checkout_url) {
        window.location.href = body.checkout_url;
        return;
      }

      setMessage(body.status === "updated" ? "Free plan selected." : "Plan updated.");
      await loadInvoices();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout session failed.");
    } finally {
      setBusyPlan(null);
    }
  }

  useEffect(() => {
    void loadInvoices();
    void loadPaymentMethod();
  }, [accessToken]);

  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <section className="page">
        <div className="page-header">
          <div>
            <h1 className="page-title">Billing and payments</h1>
            <p className="page-subtitle">Manage your plan, saved payment method, and invoice history.</p>
          </div>
          <span className="status-badge neutral">{activeAccount?.name ?? "Active account"}</span>
        </div>

        {(queryNotice || message || error) && (
          <article className="panel">
            <p className={error ? "status-text danger" : "status-text success"}>{error ?? message ?? queryNotice}</p>
          </article>
        )}

        <div className="pricing-grid">
          {plans.map((plan) => (
            <article className="price-card" key={plan.key}>
              <h3>{plan.name}</h3>
              <div className="price">
                {plan.price}
                <span>/mo</span>
              </div>
              <p>{plan.credits}</p>
              <p>{plan.detail}</p>
              <button className={plan.key === "free" ? "button secondary" : "button primary"} type="button" onClick={() => startCheckout(plan.key)} disabled={busyPlan !== null}>
                {busyPlan === plan.key ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <CreditCard size={16} aria-hidden="true" />}
                {busyPlan === plan.key ? "Opening checkout..." : plan.cta}
              </button>
            </article>
          ))}
        </div>

        <article className="panel">
          <div className="panel-header">
            <h2>Payment method</h2>
            <CreditCard size={22} color="var(--color-primary)" aria-hidden="true" />
          </div>
          {paymentMethod ? (
            <p>
              Saved card: <span className="mono">{paymentMethod.brand ?? "card"} ending {paymentMethod.last4}</span>
              {paymentMethod.exp_month && paymentMethod.exp_year ? <span> - expires {paymentMethod.exp_month}/{paymentMethod.exp_year}</span> : null}
            </p>
          ) : (
            <p>No saved card is available for this account.</p>
          )}
          <p className="muted-text">Card details are handled securely by our payment provider.</p>
          <button className="button primary" type="button" onClick={savePaymentMethod} disabled={savingCard || loadingPaymentMethod}>
            {savingCard ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <CreditCard size={16} aria-hidden="true" />}
            {paymentMethod ? "Update saved card" : "Save card"}
          </button>
        </article>

        <div className="table-panel">
          <div className="table-header">
            <h2>Invoices</h2>
            <button className="button secondary" type="button" onClick={loadInvoices} disabled={loadingInvoices}>
              <RefreshCcw size={15} className={loadingInvoices ? "spin" : undefined} aria-hidden="true" />
              Refresh
            </button>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Date</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Open</th>
              </tr>
            </thead>
            <tbody>
              {invoices.length === 0 && (
                <tr>
                  <td colSpan={5}>No invoices found for this account.</td>
                </tr>
              )}
              {invoices.map((invoice) => (
                <tr key={invoice.id}>
                  <td className="mono">{invoice.stripe_invoice_id ?? invoice.id}</td>
                  <td className="mono">{new Date(invoice.created_at).toLocaleDateString()}</td>
                  <td className="mono">{money(invoice.amount_paid || invoice.amount_due, invoice.currency)}</td>
                  <td><span className="status-badge success">{invoice.status}</span></td>
                  <td>
                    {invoice.hosted_invoice_url || invoice.invoice_pdf ? (
                      <a className="icon-button ghost" href={invoice.hosted_invoice_url ?? invoice.invoice_pdf ?? "#"} target="_blank" rel="noreferrer" aria-label="Open invoice">
                        {invoice.invoice_pdf ? <Download size={16} aria-hidden="true" /> : <ArrowUpRight size={16} aria-hidden="true" />}
                      </a>
                    ) : (
                      <span className="muted-text">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </RouteGuard>
  );
}








