"use client";

import { useState } from "react";
import { Linkedin, Plug, PlugZap } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { linkedinPosts } from "@/lib/mock-data";

export default function LinkedInPage() {
  return (
    <RouteGuard allowedRoles={["Owner", "TenantAdmin", "Member"]}>
      <LinkedInConnections />
    </RouteGuard>
  );
}

function LinkedInConnections() {
  const [connected, setConnected] = useState(true);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">LinkedIn connections</h1>
          <p className="page-subtitle">OAuth connection status and last-publish state for scheduled posts.</p>
        </div>
        <span className={connected ? "status-badge success" : "status-badge warning"}>
          {connected ? "Connected" : "Disconnected"}
        </span>
      </div>

      <article className="connection-card">
        <div className="panel-header">
          <div>
            <Linkedin size={24} color="var(--color-primary)" aria-hidden="true" />
            <h3>Company page</h3>
            <p>{connected ? "creditflow-ai" : "No active LinkedIn account"}</p>
          </div>
          <button className={connected ? "button danger" : "button primary"} type="button" onClick={() => setConnected((value) => !value)}>
            {connected ? <Plug size={16} aria-hidden="true" /> : <PlugZap size={16} aria-hidden="true" />}
            {connected ? "Disconnect" : "Connect"}
          </button>
        </div>
      </article>

      <div className="table-panel">
        <div className="table-header">
          <h2>Publish status</h2>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Post</th>
              <th>Status</th>
              <th>Last publish</th>
            </tr>
          </thead>
          <tbody>
            {linkedinPosts.map((post) => (
              <tr key={post.id}>
                <td>{post.title}</td>
                <td>
                  <span
                    className={`status-badge ${
                      post.status === "Published" ? "success" : post.status === "Failed" ? "danger" : "warning"
                    }`}
                  >
                    {post.status}
                  </span>
                </td>
                <td className="mono">{post.lastPublish}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

