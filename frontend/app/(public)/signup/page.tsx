"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { UserPlus } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await signup(email, password);
      router.push("/create-or-join");
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
            <UserPlus size={18} aria-hidden="true" />
          </span>
          CreditFlow
        </Link>
        <h1>Create your account</h1>
        <p>Enter any email and password, then choose an Individual account, Team account, or invite.</p>
        <form className="form-grid" onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="text"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
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
          Already have an account?{" "}
          <Link className="link" href="/login">
            Log in
          </Link>
        </p>
      </section>
    </main>
  );
}

