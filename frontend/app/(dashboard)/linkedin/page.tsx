"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Linkedin, Plug, PlugZap, RefreshCw } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";

type PublishJob = {
  id: string;
  content_id: string;
  status: string;
  linkedin_post_url?: string;
  last_error?: string;
  published_at?: string;
  updated_at?: string;
};

type LinkedInStatus = {
  connected: boolean;
  connection?: {
    profile_name?: string;
    email?: string;
    scopes?: string[];
    token_expires_at?: string;
    connected_at?: string;
  } | null;
  jobs: PublishJob[];
};

export default function LinkedInPage() {
  return (
    <RouteGuard allowedRoles={["Owner", "TenantAdmin", "Member"]}>
      <LinkedInConnections />
    </RouteGuard>
  );
}

function LinkedInConnections() {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState<LinkedInStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const authHeaders = () => (accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined);

  const loadStatus = async () => {
    setLoading(true);
    setMessage("");
    if (!accessToken) {
      setMessage("Please sign in before connecting LinkedIn.");
      setLoading(false);
      return;
    }
    try {
      const response = await fetch("/api/linkedin/status", { headers: authHeaders(), cache: "no-store" });
      if (!response.ok) throw new Error(`LinkedIn status failed (${response.status})`);
      setStatus((await response.json()) as LinkedInStatus);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load LinkedIn status.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, [accessToken]);

  const connect = async () => {
    setMessage("");
    if (!accessToken) {
      setMessage("Please sign in before connecting LinkedIn.");
      return;
    }
    try {
      const response = await fetch("/api/linkedin/connect", { headers: authHeaders(), cache: "no-store" });
      if (!response.ok) throw new Error(`LinkedIn connect failed (${response.status})`);
      const body = (await response.json()) as { auth_url: string };
      window.location.href = body.auth_url;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to start LinkedIn OAuth.");
    }
  };

  const disconnect = async () => {
    setMessage("");
    if (!accessToken) {
      setMessage("Please sign in before disconnecting LinkedIn.");
      return;
    }
    try {
      const response = await fetch("/api/linkedin/disconnect", { method: "DELETE", headers: authHeaders() });
      if (!response.ok) throw new Error(`LinkedIn disconnect failed (${response.status})`);
      await loadStatus();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to disconnect LinkedIn.");
    }
  };

  const connected = Boolean(status?.connected);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">LinkedIn connections</h1>
          <p className="page-subtitle">OAuth connection status and last-publish state for scheduled posts.</p>
        </div>
        <span className={connected ? "status-badge success" : "status-badge warning"}>
          {loading ? "Checking" : connected ? "Connected" : "Disconnected"}
        </span>
      </div>

      {message ? <div className="notice warning">{message}</div> : null}

      <article className="connection-card">
        <div className="panel-header">
          <div>
            <Linkedin size={24} color="var(--color-primary)" aria-hidden="true" />
            <h3>LinkedIn member account</h3>
            <p>{connected ? status?.connection?.profile_name || status?.connection?.email || "Connected LinkedIn profile" : "No active LinkedIn account"}</p>
            {connected ? <p className="muted">Scopes: {(status?.connection?.scopes ?? []).join(", ") || "not reported"}</p> : null}
          </div>
          <button className={connected ? "button danger" : "button primary"} type="button" onClick={connected ? disconnect : connect} disabled={loading}>
            {connected ? <Plug size={16} aria-hidden="true" /> : <PlugZap size={16} aria-hidden="true" />}
            {connected ? "Disconnect" : "Connect"}
          </button>
        </div>
      </article>

      <div className="table-panel">
        <div className="table-header">
          <h2>Publish status</h2>
          <button className="button secondary" type="button" onClick={loadStatus} disabled={loading}>
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </button>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Content</th>
              <th>Status</th>
              <th>Last publish</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {(status?.jobs ?? []).map((post) => (
              <tr key={post.id}>
                <td className="mono">{post.content_id}</td>
                <td>
                  <span
                    className={`status-badge ${
                      post.status === "published" ? "success" : post.status === "failed" ? "danger" : "warning"
                    }`}
                  >
                    {post.status}
                  </span>
                </td>
                <td className="mono">{post.published_at || post.updated_at || "-"}</td>
                <td>
                  {post.linkedin_post_url ? (
                    <a href={post.linkedin_post_url} target="_blank" rel="noreferrer">
                      Open <ExternalLink size={14} aria-hidden="true" />
                    </a>
                  ) : (
                    post.last_error || "-"
                  )}
                </td>
              </tr>
            ))}
            {!loading && !status?.jobs?.length ? (
              <tr>
                <td colSpan={4}>No publish jobs yet. Scheduled posts will appear here after the scheduler emits content.scheduled.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

