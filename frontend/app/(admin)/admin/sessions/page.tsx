"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, ShieldOff } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog/ConfirmDialog";
import { adminFetch, compactId, type AdminSession } from "@/lib/admin-api";
import { useAuth } from "@/lib/auth-context";

function ttlLabel(ttl?: number | null) {
  if (ttl === null || ttl === undefined) return "Unknown";
  if (ttl < 0) return "No expiry";
  if (ttl < 60) return `${ttl}s`;
  if (ttl < 3600) return `${Math.round(ttl / 60)}m`;
  return `${Math.round(ttl / 3600)}h`;
}

export default function SessionsPage() {
  const { accessToken } = useAuth();
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [accountFilter, setAccountFilter] = useState("");
  const [pendingRevoke, setPendingRevoke] = useState<AdminSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyJti, setBusyJti] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const query = accountFilter.trim() ? `?account_id=${encodeURIComponent(accountFilter.trim())}` : "";
      setSessions(await adminFetch<AdminSession[]>(`/sessions${query}`, accessToken));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load sessions.");
    } finally {
      setLoading(false);
    }
  }, [accessToken, accountFilter]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  const activeCount = useMemo(() => sessions.length, [sessions]);

  const revokeSession = async () => {
    if (!pendingRevoke) return;
    setBusyJti(pendingRevoke.jti);
    setError(null);
    try {
      await adminFetch(`/sessions/${encodeURIComponent(pendingRevoke.jti)}`, accessToken, { method: "DELETE" });
      setSessions((current) => current.filter((session) => session.jti !== pendingRevoke.jti));
      setPendingRevoke(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to revoke session.");
    } finally {
      setBusyJti(null);
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Active sessions</h1>
          <p className="page-subtitle">Live JWT session keys read from Redis. Revoking a JTI invalidates that session at the gateway.</p>
        </div>
        <span className="status-badge live">{activeCount} active</span>
      </div>

      <div className="panel search-row">
        <div className="field">
          <label htmlFor="session-account-filter">Account filter</label>
          <input id="session-account-filter" value={accountFilter} onChange={(event) => setAccountFilter(event.target.value)} placeholder="Optional account_id" />
        </div>
        <button className="button secondary" type="button" onClick={() => void loadSessions()} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={16} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error ? <div className="danger-note with-top-gap">{error}</div> : null}

      <div className="table-panel">
        <div className="table-header">
          <h2>Redis session index</h2>
          <span className="status-badge neutral">{loading ? "Loading" : `${sessions.length} rows`}</span>
        </div>
        {sessions.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>JTI</th>
                <th>Account</th>
                <th>User</th>
                <th>Role</th>
                <th>TTL</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => (
                <tr key={session.jti}>
                  <td className="mono" title={session.jti}>{compactId(session.jti, 16)}</td>
                  <td className="mono">{session.account_id ?? "—"}</td>
                  <td className="mono">{session.user_id ?? "—"}</td>
                  <td>{session.role ?? "—"}</td>
                  <td className="mono">{ttlLabel(session.ttl_seconds)}</td>
                  <td>
                    <button className="icon-button danger" type="button" aria-label={`Revoke session ${session.jti}`} disabled={busyJti === session.jti} onClick={() => setPendingRevoke(session)}>
                      <ShieldOff size={16} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">{loading ? "Loading active sessions…" : "No active sessions found."}</div>
        )}
      </div>

      <ConfirmDialog open={!!pendingRevoke} title="Revoke session" message={`Revoke ${pendingRevoke?.jti ?? "this session"}?`} confirmLabel="Revoke" onCancel={() => setPendingRevoke(null)} onConfirm={() => void revokeSession()} />
    </section>
  );
}
