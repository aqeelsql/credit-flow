"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MailCheck } from "lucide-react";
import { apiFetch } from "@/lib/api-client";

const USE_LOCAL_AUTH = process.env.NEXT_PUBLIC_USE_LOCAL_AUTH !== "false";

export default function VerifyEmailPage() {
  const [status, setStatus] = useState<"checking" | "success" | "failure">("checking");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");

    if (!token && USE_LOCAL_AUTH) {
      setStatus("success");
      return;
    }

    if (!token) {
      setStatus("failure");
      return;
    }

    apiFetch("/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
      skipAuth: true
    })
      .then(() => setStatus("success"))
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
            Email verification UI is ready.{" "}
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
