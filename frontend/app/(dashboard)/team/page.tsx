"use client";

import { useCallback, useEffect, useState } from "react";
import { MailPlus, Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog/ConfirmDialog";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";
import type { AccountRole, TeamMember } from "@/lib/types";

type TeamRow = { id: string; name?: string; email: string; role: AccountRole; status: "Active" | "Invited" | string };

async function api<T>(path: string, token: string | null, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error(response.statusText || "Team request failed.");
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export default function TeamPage() {
  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <TeamManagement />
    </RouteGuard>
  );
}

function TeamManagement() {
  const { activeAccount, accessToken } = useAuth();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [pendingRemoval, setPendingRemoval] = useState<TeamMember | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMembers = useCallback(async () => {
    if (!activeAccount?.id) return;
    setError(null);
    try {
      const rows = await api<TeamRow[]>(`/api/accounts/${activeAccount.id}/team`, accessToken);
      setMembers(rows.map((row) => ({ id: row.id, name: row.name || row.email.split("@")[0], email: row.email, role: row.role, status: row.status === "Invited" ? "Invited" : "Active" })));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load members.");
    }
  }, [accessToken, activeAccount?.id]);

  useEffect(() => { void loadMembers(); }, [loadMembers]);

  const inviteMember = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!activeAccount?.id) return;
    setError(null);
    try {
      await api(`/api/accounts/${activeAccount.id}/invites`, accessToken, { method: "POST", body: JSON.stringify({ email: inviteEmail, role: "Member" }) });
      setInviteEmail("");
      await loadMembers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to invite member.");
    }
  };

  const updateRole = async (member: TeamMember, role: TeamMember["role"]) => {
    if (!activeAccount?.id) return;
    setError(null);
    try {
      await api(`/api/accounts/${activeAccount.id}/members/${member.id}`, accessToken, { method: "PATCH", body: JSON.stringify({ role }) });
      await loadMembers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update member role.");
    }
  };

  const removeMember = async () => {
    if (!activeAccount?.id || !pendingRemoval) return;
    setError(null);
    try {
      await api(`/api/accounts/${activeAccount.id}/members/${pendingRemoval.id}`, accessToken, { method: "DELETE" });
      setPendingRemoval(null);
      await loadMembers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove member.");
    }
  };

  return (
    <section className="page">
      <div className="page-header"><div><h1 className="page-title">Team management</h1><p className="page-subtitle">Invite members, change roles, and remove real account access.</p></div></div>
      <form className="panel search-row" onSubmit={inviteMember} noValidate>
        <div className="field"><label htmlFor="invite-email">Invite by email</label><input id="invite-email" type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} required /></div>
        <button className="button primary" type="submit"><MailPlus size={16} aria-hidden="true" />Invite</button>
      </form>
      {error ? <div className="danger-note with-top-gap">{error}</div> : null}
      <div className="table-panel">
        <div className="table-header"><h2>Members</h2><span className="status-badge neutral">{members.length} members</span></div>
        {members.length ? <table className="data-table"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Action</th></tr></thead><tbody>{members.map((member) => <tr key={member.id}><td>{member.name}</td><td>{member.email}</td><td><select className="select" value={member.role} disabled={member.role === "Owner"} onChange={(event) => void updateRole(member, event.target.value as TeamMember["role"])}><option value="TenantAdmin">Admin</option><option value="Member">Member</option><option value="Owner">Owner</option></select></td><td><span className={`status-badge ${member.status === "Active" ? "success" : "warning"}`}>{member.status}</span></td><td><button className="icon-button danger" type="button" aria-label={`Remove ${member.name}`} disabled={member.role === "Owner"} onClick={() => setPendingRemoval(member)}><Trash2 size={16} aria-hidden="true" /></button></td></tr>)}</tbody></table> : <div className="empty-state">No team members returned yet.</div>}
      </div>
      <ConfirmDialog open={!!pendingRemoval} title="Remove member" message={`Remove ${pendingRemoval?.email ?? "this member"} from the active account?`} confirmLabel="Remove" onCancel={() => setPendingRemoval(null)} onConfirm={() => void removeMember()} />
    </section>
  );
}
