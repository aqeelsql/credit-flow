"use client";

import { useCallback, useEffect, useState } from "react";
import { FileClock, RefreshCw } from "lucide-react";
import { adminFetch, compactId, type AdminAuditItem, type AdminAuditResponse } from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function AuditLogPage() {
  const { accessToken } = useAuth();
  const [query, setQuery] = useState("");
  const [accountId, setAccountId] = useState("");
  const [rows, setRows] = useState<AdminAuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: "75" });
    if (query.trim()) params.set("q", query.trim());
    if (accountId.trim()) params.set("account_id", accountId.trim());
    try {
      const response = await adminFetch<AdminAuditResponse>(`/audit-log?${params.toString()}`, accessToken);
      setRows(response.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load audit log.");
    } finally {
      setLoading(false);
    }
  }, [accessToken, accountId, query]);

  useEffect(() => {
    void loadAudit();
  }, [loadAudit]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit log</h1>
          <p className="page-subtitle">Searchable timeline of domain events captured by the Admin/Ops wildcard RabbitMQ consumer.</p>
        </div>
        <span className="status-badge neutral">{rows.length} events</span>
      </div>

      <div className="panel search-row">
        <div className="admin-filter-grid">
          <div className="field">
            <label htmlFor="audit-search">Search</label>
            <input id="audit-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Event, actor, routing key, or payload text" />
          </div>
          <div className="field">
            <label htmlFor="audit-account">Account</label>
            <input id="audit-account" value={accountId} onChange={(event) => setAccountId(event.target.value)} placeholder="Optional account_id" />
          </div>
        </div>
        <button className="button secondary" type="button" onClick={() => void loadAudit()} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={16} aria-hidden="true" />
          Search
        </button>
      </div>

      {error ? <div className="danger-note with-top-gap">{error}</div> : null}

      <article className="panel with-top-gap">
        <div className="panel-header">
          <h2>Platform timeline</h2>
          <FileClock size={22} color="var(--color-primary)" aria-hidden="true" />
        </div>
        {rows.length ? (
          <div className="timeline-list">
            {rows.map((row) => (
              <div className="timeline-item" key={row.id}>
                <div className="timeline-time">{formatDate(row.created_at)}</div>
                <div>
                  <strong>{row.action || row.routing_key}</strong>
                  <p>
                    <span className="mono">{row.account_id ?? "platform"}</span> / actor <span className="mono">{row.actor_user_id ?? "system"}</span>
                  </p>
                  <p>
                    {row.summary ?? row.routing_key} · <span className="mono">{row.exchange ?? "exchange"}</span> · event <span className="mono" title={row.event_id}>{compactId(row.event_id, 14)}</span>
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">{loading ? "Loading audit events…" : "No audit events found yet."}</div>
        )}
      </article>
    </section>
  );
}
