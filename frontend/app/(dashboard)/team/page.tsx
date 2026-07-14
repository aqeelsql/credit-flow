"use client";

import { useState } from "react";
import { MailPlus, Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog/ConfirmDialog";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { teamMembers as initialMembers } from "@/lib/mock-data";
import type { TeamMember } from "@/lib/types";

export default function TeamPage() {
  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <TeamManagement />
    </RouteGuard>
  );
}

function TeamManagement() {
  const [members, setMembers] = useState<TeamMember[]>(initialMembers);
  const [inviteEmail, setInviteEmail] = useState("");
  const [pendingRemoval, setPendingRemoval] = useState<TeamMember | null>(null);

  const inviteMember = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMembers((current) => [
      ...current,
      {
        id: `mem_${Date.now()}`,
        name: inviteEmail.split("@")[0] || "Invited member",
        email: inviteEmail,
        role: "Member",
        status: "Invited"
      }
    ]);
    setInviteEmail("");
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Team management</h1>
          <p className="page-subtitle">Invite members, change roles, and remove account access.</p>
        </div>
      </div>

      <form className="panel search-row" onSubmit={inviteMember} noValidate>
        <div className="field">
          <label htmlFor="invite-email">Invite by email</label>
          <input
            id="invite-email"
            type="text"
            value={inviteEmail}
            onChange={(event) => setInviteEmail(event.target.value)}
          />
        </div>
        <button className="button primary" type="submit">
          <MailPlus size={16} aria-hidden="true" />
          Invite
        </button>
      </form>

      <div className="table-panel">
        <div className="table-header">
          <h2>Members</h2>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.id}>
                <td>{member.name}</td>
                <td>{member.email}</td>
                <td>
                  <select
                    className="select"
                    value={member.role}
                    disabled={member.role === "Owner"}
                    onChange={(event) =>
                      setMembers((current) =>
                        current.map((item) =>
                          item.id === member.id ? { ...item, role: event.target.value as TeamMember["role"] } : item
                        )
                      )
                    }
                  >
                    <option value="TenantAdmin">Admin</option>
                    <option value="Member">Member</option>
                    <option value="Owner">Owner</option>
                  </select>
                </td>
                <td>
                  <span className={`status-badge ${member.status === "Active" ? "success" : "warning"}`}>
                    {member.status}
                  </span>
                </td>
                <td>
                  <button
                    className="icon-button danger"
                    type="button"
                    aria-label={`Remove ${member.name}`}
                    disabled={member.role === "Owner"}
                    onClick={() => setPendingRemoval(member)}
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!pendingRemoval}
        title="Remove member"
        message={`Remove ${pendingRemoval?.email ?? "this member"} from the active account?`}
        confirmLabel="Remove"
        onCancel={() => setPendingRemoval(null)}
        onConfirm={() => {
          if (pendingRemoval) {
            setMembers((current) => current.filter((member) => member.id !== pendingRemoval.id));
          }
          setPendingRemoval(null);
        }}
      />
    </section>
  );
}



