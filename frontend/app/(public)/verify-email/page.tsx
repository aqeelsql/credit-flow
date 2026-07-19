"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MailCheck } from "lucide-react";

export default function VerifyEmailPage() {
  const [status, setStatus] = useState<"checking" | "success" | "failure">("checking");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");

    if (!token) {
      setStatus("failure");
      return;
    }

    fetch("/api/auth/verify-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token })
    })
      .then((response) => setStatus(response.ok ? "success" : "failure"))
      .catch(() => setStatus("failure"));
  }, []);

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <MailCheck size={18} aria-hidden="true" />
          </span>
          CreditFlow
        </Link>
        <h1>Email verification</h1>
        {status === "checking" ? <p>Activating your account...</p> : null}
        {status === "success" ? (
          <div className="success-note">
            Your email is verified. You can now log in.{" "}
            <Link className="link" href="/login">
              Continue to login
            </Link>
          </div>
        ) : null}
        {status === "failure" ? (
          <div className="danger-note">This verification link is missing, expired, or invalid.</div>
        ) : null}
      </section>
    </main>
  );
}
