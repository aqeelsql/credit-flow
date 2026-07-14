"use client";

import { useState } from "react";
import { CircleDollarSign, Plus, ShoppingCart } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { marketplaceListings, ownListings } from "@/lib/mock-data";
import type { CreditListing } from "@/lib/types";

export default function CreditsPage() {
  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <CreditsMarketplace />
    </RouteGuard>
  );
}

function CreditsMarketplace() {
  const [listings, setListings] = useState<CreditListing[]>(ownListings);
  const [credits, setCredits] = useState(2000);
  const [price, setPrice] = useState("21.00");
  const [notice, setNotice] = useState("");

  const addListing = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setListings((current) => [
      ...current,
      {
        id: `own_${Date.now()}`,
        seller: "Active account",
        credits,
        price: `$${price}`,
        status: "Listed"
      }
    ]);
    setNotice("Credits listed in marketplace.");
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Credits and marketplace</h1>
          <p className="page-subtitle">Buy credits, list surplus credits, and purchase from other accounts.</p>
        </div>
        <button className="button primary" type="button" onClick={() => setNotice("Redirecting to Stripe Checkout...")}>
          <ShoppingCart size={16} aria-hidden="true" />
          Buy credits
        </button>
      </div>

      {notice ? <div className="notice">{notice}</div> : null}

      <div className="split-layout with-top-gap">
        <form className="panel form-grid" onSubmit={addListing}>
          <CircleDollarSign size={22} color="var(--color-primary)" aria-hidden="true" />
          <h2>List surplus credits</h2>
          <div className="field">
            <label htmlFor="credits">Credits</label>
            <input
              id="credits"
              type="number"
              min={100}
              step={100}
              value={credits}
              onChange={(event) => setCredits(Number(event.target.value))}
            />
          </div>
          <div className="field">
            <label htmlFor="price">Price</label>
            <input id="price" value={price} onChange={(event) => setPrice(event.target.value)} />
          </div>
          <button className="button secondary" type="submit">
            <Plus size={16} aria-hidden="true" />
            List credits
          </button>
        </form>

        <div className="stack">
          <div className="table-panel">
            <div className="table-header">
              <h2>Your listings</h2>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Credits</th>
                  <th>Price</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {listings.map((listing) => (
                  <tr key={listing.id}>
                    <td className="mono">{listing.credits.toLocaleString()}</td>
                    <td className="mono">{listing.price}</td>
                    <td>
                      <span className="status-badge live">{listing.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="table-panel">
            <div className="table-header">
              <h2>Marketplace</h2>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Seller</th>
                  <th>Credits</th>
                  <th>Price</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {marketplaceListings.map((listing) => (
                  <tr key={listing.id}>
                    <td>{listing.seller}</td>
                    <td className="mono">{listing.credits.toLocaleString()}</td>
                    <td className="mono">{listing.price}</td>
                    <td>
                      <button className="button secondary" type="button" onClick={() => setNotice("Purchase queued.")}>
                        Buy
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}