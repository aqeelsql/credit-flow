"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LogIn } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import type { AccountRole } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submitLogin = async () => {
    setError("");
    setIsSubmitting(true);
    try {
      const actualRole: AccountRole = await login(email, password);
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(next ?? (actualRole === "SuperAdmin" ? "/admin/usage" : actualRole === "Member" ? "/content-studio" : "/dashboard"));
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
        <p>Enter your email and password. The system will validate your account and open the correct workspace for your role.</p>
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

