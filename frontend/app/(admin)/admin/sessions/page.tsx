"use client";

import { useState } from "react";
import { ShieldOff } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog/ConfirmDialog";
import { activeSessions as initialSessions } from "@/lib/mock-data";
import type { ActiveSession } from "@/lib/types";

export default function SessionsPage() {
  const [sessions, setSessions] = useState<ActiveSession[]>(initialSessions);
  const [pendingRevoke, setPendingRevoke] = useState<ActiveSession | null>(null);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Active sessions</h1>
          <p className="page-subtitle">JWT sessions per account, sourced from the backend Redis session index.</p>
        </div>
        <span className="status-badge live">{sessions.filter((session) => session.status === "Active").length} active</span>
      </div>

      <div className="table-panel">
        <div className="table-header">
          <h2>Sessions</h2>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>JTI</th>
              <th>Account</th>
              <th>User</th>
              <th>Role</th>
              <th>Started</th>
              <th>Last seen</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((session) => (
              <tr key={session.id}>
                <td className="mono">{session.id}</td>
                <td>{session.account}</td>
                <td>{session.user}</td>
                <td>{session.role}</td>
                <td className="mono">{session.startedAt}</td>
                <td className="mono">{session.lastSeen}</td>
                <td>
                  <span className={session.status === "Active" ? "status-badge live" : "status-badge neutral"}>
                    {session.status}
                  </span>
                </td>
                <td>
                  <button
                    className="icon-button danger"
                    type="button"
                    aria-label={`Revoke session ${session.id}`}
                    disabled={session.status === "Revoked"}
                    onClick={() => setPendingRevoke(session)}
                  >
                    <ShieldOff size={16} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!pendingRevoke}
        title="Revoke session"
        message={`Revoke ${pendingRevoke?.id ?? "this session"} for ${pendingRevoke?.account ?? "this account"}?`}
        confirmLabel="Revoke"
        onCancel={() => setPendingRevoke(null)}
        onConfirm={() => {
          if (pendingRevoke) {
            setSessions((current) =>
              current.map((session) =>
                session.id === pendingRevoke.id ? { ...session, status: "Revoked" } : session
              )
            );
          }
          setPendingRevoke(null);
        }}
      />
    </section>
  );
}
