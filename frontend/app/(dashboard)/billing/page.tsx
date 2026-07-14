"use client";

import { CreditCard, Download } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { invoices } from "@/lib/mock-data";

const plans = [
  { name: "Starter", price: "$29", credits: "4,000 credits", state: "Available" },
  { name: "Pro", price: "$149", credits: "25,000 credits", state: "Current" },
  { name: "Scale", price: "$399", credits: "90,000 credits", state: "Upgrade" }
];

export default function BillingPage() {
  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <section className="page">
        <div className="page-header">
          <div>
            <h1 className="page-title">Billing and invoices</h1>
            <p className="page-subtitle">Manage the subscription plan, payment method, and invoice history.</p>
          </div>
          <span className="status-badge success">Card ending 4242</span>
        </div>

        <div className="pricing-grid">
          {plans.map((plan) => (
            <article className="price-card" key={plan.name}>
              <h3>{plan.name}</h3>
              <div className="price">
                {plan.price}
                <span>/mo</span>
              </div>
              <p>{plan.credits}</p>
              <button className={plan.state === "Current" ? "button secondary" : "button primary"} type="button">
                {plan.state}
              </button>
            </article>
          ))}
        </div>

        <article className="panel">
          <div className="panel-header">
            <h2>Payment method</h2>
            <CreditCard size={22} color="var(--color-primary)" aria-hidden="true" />
          </div>
          <p>Visa card ending in 4242. Renewal date: <span className="mono">2026-08-01</span>.</p>
        </article>

        <div className="table-panel">
          <div className="table-header">
            <h2>Invoices</h2>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Date</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((invoice) => (
                <tr key={invoice.id}>
                  <td className="mono">{invoice.id}</td>
                  <td className="mono">{invoice.date}</td>
                  <td className="mono">{invoice.amount}</td>
                  <td>
                    <span className="status-badge success">{invoice.status}</span>
                  </td>
                  <td>
                    <button className="icon-button ghost" type="button" aria-label={`Download ${invoice.id}`}>
                      <Download size={16} aria-hidden="true" />
                    </button>
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
