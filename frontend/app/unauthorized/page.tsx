import Link from "next/link";

export default function UnauthorizedPage() {
  return (
    <main className="auth-shell">
      <section className="auth-card">
        <span className="eyebrow">Access control</span>
        <h1>Unauthorized</h1>
        <p>Your current role does not include access to this page for the active account.</p>
        <div className="button-row">
          <Link className="button primary" href="/content-studio">
            Go to content studio
          </Link>
          <Link className="button ghost" href="/login">
            Log in again
          </Link>
        </div>
      </section>
    </main>
  );
}
