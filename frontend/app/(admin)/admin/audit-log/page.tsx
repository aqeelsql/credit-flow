"use client";

import { useMemo, useState } from "react";
import { FileClock } from "lucide-react";
import { auditRows } from "@/lib/mock-data";

export default function AuditLogPage() {
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const normalized = query.toLowerCase();
    return auditRows.filter(
      (row) =>
        row.account.toLowerCase().includes(normalized) ||
        row.actor.toLowerCase().includes(normalized) ||
        row.event.toLowerCase().includes(normalized)
    );
  }, [query]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit log</h1>
          <p className="page-subtitle">Searchable domain events emitted by account services.</p>
        </div>
      </div>

      <div className="panel search-row">
        <div className="field">
          <label htmlFor="audit-search">Search</label>
          <input
            id="audit-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Account, actor, or event"
          />
        </div>
        <FileClock size={22} color="var(--color-primary)" aria-hidden="true" />
      </div>

      <article className="panel">
        <div className="panel-header">
          <h2>Timeline</h2>
          <span className="status-badge neutral">{rows.length} events</span>
        </div>
        <div className="timeline-list">
          {rows.map((row) => (
            <div className="timeline-item" key={row.id}>
              <div className="timeline-time">{row.timestamp}</div>
              <div>
                <strong>{row.event}</strong>
                <p>
                  {row.account} / {row.actor}
                </p>
              </div>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}
