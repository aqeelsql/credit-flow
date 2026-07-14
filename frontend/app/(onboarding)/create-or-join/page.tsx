"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Building2, UserRoundPlus, Users } from "lucide-react";
import { AccountSwitcher } from "@/components/AccountSwitcher/AccountSwitcher";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";

export default function CreateOrJoinPage() {
  return (
    <RouteGuard allowedRoles={["Owner", "TenantAdmin", "Member", "SuperAdmin"]} requireAccount={false}>
      <CreateOrJoinContent />
    </RouteGuard>
  );
}

function CreateOrJoinContent() {
  const router = useRouter();
  const { createAccount, acceptInvite, activeAccount, session } = useAuth();
  const [individualName, setIndividualName] = useState("My Studio");
  const [teamName, setTeamName] = useState("New Team");
  const [inviteCode, setInviteCode] = useState("");

  const finish = () => router.push("/content-studio");

  return (
    <main className="auth-shell">
      <section className="auth-card wide">
        <div className="panel-header">
          <Link className="brand" href="/">
            <span className="brand-mark">
              <Building2 size={18} aria-hidden="true" />
            </span>
            CreditFlow
          </Link>
          <AccountSwitcher />
        </div>
        <h1>Create or join account</h1>
        <p>
          {activeAccount
            ? `Current scope is ${activeAccount.name}.`
            : session?.role === "SuperAdmin"
              ? "Platform administrators can browse the admin console."
              : "Choose the account scope to use before entering the dashboard."}
        </p>
        <div className="card-grid">
          <form
            className="panel form-grid"
            onSubmit={async (event) => {
              event.preventDefault();
              await createAccount("individual", individualName);
              finish();
            }}
          >
            <UserRoundPlus size={22} color="var(--color-primary)" aria-hidden="true" />
            <h2>Individual</h2>
            <p>Creates an individual account with one owner member.</p>
            <div className="field">
              <label htmlFor="individual-name">Account name</label>
              <input
                id="individual-name"
                value={individualName}
                onChange={(event) => setIndividualName(event.target.value)}
                required
              />
            </div>
            <button className="button primary" type="submit">
              Create individual account
            </button>
          </form>
          <form
            className="panel form-grid"
            onSubmit={async (event) => {
              event.preventDefault();
              await createAccount("team", teamName);
              finish();
            }}
          >
            <Users size={22} color="var(--color-primary)" aria-hidden="true" />
            <h2>Team</h2>
            <p>Creates a team account where owners can invite members and assign roles.</p>
            <div className="field">
              <label htmlFor="team-name">Team name</label>
              <input id="team-name" value={teamName} onChange={(event) => setTeamName(event.target.value)} required />
            </div>
            <button className="button primary" type="submit">
              Create team account
            </button>
          </form>
        </div>
        <form
          className="panel form-grid"
          onSubmit={async (event) => {
            event.preventDefault();
            await acceptInvite(inviteCode);
            finish();
          }}
        >
          <h2>Accept invite</h2>
          <div className="search-row">
            <input
              className="input"
              placeholder="Invite code"
              value={inviteCode}
              onChange={(event) => setInviteCode(event.target.value)}
              required
            />
            <button className="button secondary" type="submit">
              Join team
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
