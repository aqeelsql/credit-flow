"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import type { AccountRole } from "@/lib/types";

export default function SuperAdminLoginPage() {
  const router = useRouter();
  const { login, logout } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submitLogin = async () => {
    setError("");
    setIsSubmitting(true);
    try {
      const role: AccountRole = await login(email, password);
      if (role !== "SuperAdmin") {
        logout();
        setError("This route is only for SuperAdmin accounts.");
        return;
      }
      router.push("/admin/directory");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to enter the admin console.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <ShieldCheck size={18} aria-hidden="true" />
          </span>
          CreditFlow Admin
        </Link>
        <h1>SuperAdmin login</h1>
        <p>This restricted route is for platform administrators whose email is configured in the system.</p>
        <form
          className="form-grid"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void submitLogin();
          }}
        >
          <div className="field">
            <label htmlFor="superadmin-email">Email</label>
            <input id="superadmin-email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="superadmin-password">Password</label>
            <input id="superadmin-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </div>
          {error ? <div className="danger-note">{error}</div> : null}
          <button className="button primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Checking admin access..." : "Enter admin console"}
          </button>
        </form>
      </section>
    </main>
  );
}
