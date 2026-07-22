"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";

export default function ForgotPasswordPage() {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(300);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const emailParam = params.get("email")?.trim();
    if (emailParam) setEmail(emailParam);
  }, []);

  useEffect(() => {
    if (step !== 2) return;
    const timer = window.setInterval(() => {
      setSecondsLeft((current) => Math.max(current - 1, 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [step]);

  const requestOtp = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const response = await fetch("/api/auth/forgot-password/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
        cache: "no-store"
      });
      if (!response.ok) throw new Error(await readError(response));
      setSecondsLeft(300);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to send reset email.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const verifyOtp = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!otp.trim()) {
      setError("Enter the one-time code from your email.");
      return;
    }
    setError("");
    setStep(3);
  };

  const resetPassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const response = await fetch("/api/auth/forgot-password/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), otp: otp.trim(), password }),
        cache: "no-store"
      });
      if (!response.ok) throw new Error(await readError(response));
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reset password.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <KeyRound size={18} aria-hidden="true" />
          </span>
          CreditFlow
        </Link>
        <h1>Reset password</h1>
        <p>Enter your email and we will send a one-time reset code. Codes can be used once and expire quickly.</p>

        {error ? <div className="danger-note">{error}</div> : null}

        {done ? (
          <div className="success-note">
            Password reset complete.{" "}
            <Link className="link" href="/login">
              Log in
            </Link>
          </div>
        ) : null}

        {!done && step === 1 ? (
          <form className="form-grid" onSubmit={requestOtp} noValidate>
            <div className="field">
              <label htmlFor="reset-email">Email</label>
              <input id="reset-email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </div>
            <button className="button primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Sending code..." : "Send reset code"}
            </button>
          </form>
        ) : null}

        {!done && step === 2 ? (
          <form className="form-grid" onSubmit={verifyOtp} noValidate>
            <div className="success-note">If this email is registered, the reset code has been sent.</div>
            <div className="warning-note">
              Code expires in <span className="mono">{Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}</span>.
            </div>
            <div className="field">
              <label htmlFor="otp">One-time code</label>
              <input id="otp" inputMode="numeric" value={otp} onChange={(event) => setOtp(event.target.value)} required />
            </div>
            <button className="button primary" type="submit" disabled={secondsLeft === 0}>
              Continue
            </button>
          </form>
        ) : null}

        {!done && step === 3 ? (
          <form className="form-grid" onSubmit={resetPassword} noValidate>
            <div className="field">
              <label htmlFor="new-password">New password</label>
              <input id="new-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            </div>
            <button className="button primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Resetting..." : "Set new password"}
            </button>
          </form>
        ) : null}

        <p>
          Remembered it?{" "}
          <Link className="link" href="/login">
            Back to login
          </Link>
        </p>
      </section>
    </main>
  );
}

async function readError(response: Response) {
  try {
    const body = (await response.json()) as { message?: string; error?: string | { message?: string } };
    if (body.message) return body.message;
    if (typeof body.error === "string") return body.error;
    if (typeof body.error === "object" && body.error?.message) return body.error.message;
  } catch {
    // Use status text below.
  }
  return response.statusText || "Request failed.";
}
