"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LogIn } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import type { AccountRole } from "@/lib/types";

const loginRoles: Array<{ label: string; value: AccountRole; description: string }> = [
  { label: "Owner", value: "Owner", description: "Owner-only pages plus content tools." },
  { label: "Member", value: "Member", description: "Content, calendar, and LinkedIn tools." },
  { label: "SuperAdmin", value: "SuperAdmin", description: "Platform admin console." }
];

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AccountRole>("Owner");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submitLogin = async () => {
    setError("");
    setIsSubmitting(true);
    try {
      await login(email, password, role);
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(next ?? (role === "SuperAdmin" ? "/admin/directory" : "/content-studio"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to enter the app.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <LogIn size={18} aria-hidden="true" />
          </span>
          CreditFlow
        </Link>
        <h1>Log in</h1>
        <p>Enter anything and choose the role you want to preview.</p>
        <form
          className="form-grid"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void submitLogin();
          }}
        >
          <div className="field">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="text"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <div className="field">
            <span className="label">Preview role</span>
            <div className="role-choice-grid" role="radiogroup" aria-label="Preview role">
              {loginRoles.map((item) => (
                <button
                  key={item.value}
                  className={`role-choice ${role === item.value ? "active" : ""}`}
                  type="button"
                  role="radio"
                  aria-checked={role === item.value}
                  onClick={() => setRole(item.value)}
                >
                  <strong>{item.label}</strong>
                  <span>{item.description}</span>
                </button>
              ))}
            </div>
          </div>
          {error ? <div className="danger-note">{error}</div> : null}
          <button className="button primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Entering..." : "Continue"}
          </button>
        </form>
        <p>
          Need onboarding?{" "}
          <Link className="link" href="/signup">
            Sign up
          </Link>
        </p>
      </section>
    </main>
  );
}
