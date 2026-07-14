"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { apiFetch } from "@/lib/api-client";

export default function ForgotPasswordPage() {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(300);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (step !== 2) {
      return;
    }

    const timer = window.setInterval(() => {
      setSecondsLeft((current) => Math.max(current - 1, 0));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [step]);

  const requestOtp = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await apiFetch("/auth/forgot-password/request", {
      method: "POST",
      body: JSON.stringify({ email }),
      skipAuth: true
    });
    setSecondsLeft(300);
    setStep(2);
  };

  const verifyOtp = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStep(3);
  };

  const resetPassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await apiFetch("/auth/forgot-password/reset", {
      method: "POST",
      body: JSON.stringify({ email, otp, password }),
      skipAuth: true
    });
    setDone(true);
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
        <p>One-time codes expire quickly and can be used once.</p>

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
              <input
                id="reset-email"
                type="text"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <button className="button primary" type="submit">
              Request one-time code
            </button>
          </form>
        ) : null}

        {!done && step === 2 ? (
          <form className="form-grid" onSubmit={verifyOtp} noValidate>
            <div className="warning-note">
              Code expires in <span className="mono">{Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}</span>.
            </div>
            <div className="field">
              <label htmlFor="otp">One-time code</label>
              <input id="otp" value={otp} onChange={(event) => setOtp(event.target.value)} />
            </div>
            <button className="button primary" type="submit" disabled={secondsLeft === 0}>
              Verify code
            </button>
          </form>
        ) : null}

        {!done && step === 3 ? (
          <form className="form-grid" onSubmit={resetPassword} noValidate>
            <div className="field">
              <label htmlFor="new-password">New password</label>
              <input
                id="new-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            <button className="button primary" type="submit">
              Set new password
            </button>
          </form>
        ) : null}
      </section>
    </main>
  );
}


