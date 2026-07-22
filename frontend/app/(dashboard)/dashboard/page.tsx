"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowUpRight, CalendarClock, CheckCircle, Coins, FileText, RefreshCw, Send, Sparkles, Users, WalletCards, Zap } from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";
import { useAuth } from "@/lib/auth-context";
import type { AccountRole } from "@/lib/types";

type BalanceResponse = { balance: number; low_balance_threshold?: number; is_low_balance?: boolean };
type CreditTransaction = { id: string; amount: number; reason: string; source_event_id?: string | null; metadata?: Record<string, unknown>; created_at: string };

async function readError(response: Response) {
  try {
    const body = (await response.json()) as { error?: string | { message?: string }; message?: string };
    return body.message || (typeof body.error === "string" ? body.error : body.error?.message) || response.statusText;
  } catch {
    return response.statusText;
  }
}

async function api<T>(path: string, token: string | null) {
  const response = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    cache: "no-store"
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<T>;
}

function metadataString(metadata: Record<string, unknown> | null | undefined, keys: string[], fallback = "Unknown") {
  for (const key of keys) {
    const value = metadata?.[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number") return String(value);
  }
  return fallback;
}

function preview(text?: string | null, limit = 96) {
  const compact = (text ?? "").replace(/\s+/g, " ").trim();
  if (!compact) return "No preview recorded";
  return compact.length > limit ? `${compact.slice(0, limit)}...` : compact;
}

export default function DashboardPage() {
  return (
    <RouteGuard allowedRoles={["Owner"]}>
      <OwnerDashboard />
    </RouteGuard>
  );
}

function OwnerDashboard() {
  const { activeAccount, accessToken, session } = useAuth();
  const [balance, setBalance] = useState<number | null>(null);
  const [purchases, setPurchases] = useState<CreditTransaction[]>([]);
  const [creditsUsed, setCreditsUsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    if (!activeAccount?.id || !accessToken) return;
    setIsLoading(true);
    setError(null);
    try {
      const [balanceResponse, transactions, team, draftResponse, approvedResponse, publishedResponse] = await Promise.all([
        api<BalanceResponse>("/api/credits/balance", accessToken),
        api<CreditLedgerEntry[]>("/api/credits/transactions?limit=200", accessToken),
        api<TeamRow[]>(`/api/accounts/${activeAccount.id}/team`, accessToken),
        api<DraftListResponse>("/api/content/drafts?status=draft&limit=100", accessToken),
        api<DraftListResponse>("/api/content/drafts?status=approved&limit=100", accessToken),
        api<DraftListResponse>("/api/content/drafts?status=published&limit=100", accessToken)
      ]);
      setBalance(balanceResponse.balance);
      setLedgerRows(transactions.filter((row) => row.amount < 0 && row.metadata?.kind === "ai_generation"));
      setTeamMembers(team);
      const byId = new Map<string, DraftItem>();
      [...(draftResponse.items ?? []), ...(approvedResponse.items ?? []), ...(publishedResponse.items ?? [])].forEach((item) => byId.set(item.id, item));
      setContentItems([...byId.values()].sort((a, b) => String(b.updated_at ?? b.created_at ?? "").localeCompare(String(a.updated_at ?? a.created_at ?? ""))));
      setLastUpdated(new Date().toLocaleTimeString());
      setReviewItem((current) => current ? ([...byId.values()].find((item) => item.id === current.id) ?? null) : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load dashboard activity.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, activeAccount?.id]);

  useEffect(() => {
    if (!accessToken) return;
    const load = async () => {
      setError(null);
      const response = await fetch("/api/credits/balance", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" });
      if (!response.ok) throw new Error(await readError(response));
      const data = (await response.json()) as BalanceResponse;
      setBalance(data.balance);
      const txResponse = await fetch("/api/credits/transactions?limit=10", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" });
      if (txResponse.ok) {
        const transactions = (await txResponse.json()) as CreditTransaction[];
        setPurchases(transactions.filter((item) => item.amount > 0 && item.reason === "purchase").slice(0, 5));
        setCreditsUsed(transactions.filter((item) => item.amount < 0).reduce((sum, item) => sum + Math.abs(item.amount), 0));
      }
    };
  }, [loadDashboard]);

  const memberByUserId = useMemo(() => {
    const map = new Map<string, TeamRow>();
    teamMembers.forEach((member) => {
      if (member.user_id) map.set(member.user_id, member);
    });
    return map;
  }, [teamMembers]);

  const memberUsage = useMemo(() => {
    const rows = new Map<string, MemberUsage>();
    teamMembers.forEach((member) => {
      const key = member.user_id || member.email;
      rows.set(key, {
        key,
        name: member.name || member.email.split("@")[0],
        email: member.email,
        role: member.role,
        creditsUsed: 0,
        generations: 0
      });
    });
    ledgerRows.forEach((entry) => {
      const userId = metadataString(entry.metadata, ["user_id"], "");
      const email = metadataString(entry.metadata, ["user_email"], "");
      const key = userId || email || "unknown";
      const member = userId ? memberByUserId.get(userId) : undefined;
      const existing = rows.get(key) ?? {
        key,
        name: member?.name || email.split("@")[0] || userId || "Unknown user",
        email: member?.email || email || "Unknown email",
        role: member?.role || metadataString(entry.metadata, ["role"], "Member"),
        creditsUsed: 0,
        generations: 0
      };
      existing.creditsUsed += Math.abs(entry.amount);
      existing.generations += 1;
      if (!existing.lastActivity || entry.created_at > existing.lastActivity) existing.lastActivity = entry.created_at;
      rows.set(key, existing);
    });
    return [...rows.values()].sort((a, b) => b.creditsUsed - a.creditsUsed || a.name.localeCompare(b.name));
  }, [ledgerRows, memberByUserId, teamMembers]);

  const totalAiCreditsUsed = useMemo(() => ledgerRows.reduce((sum, row) => sum + Math.abs(row.amount), 0), [ledgerRows]);
  const activeCreators = useMemo(() => new Set(contentItems.map((item) => item.created_by_user_id).filter(Boolean)).size, [contentItems]);
  const activeTeamMembers = useMemo(() => teamMembers.filter((member) => member.role !== "Owner" && member.status !== "removed"), [teamMembers]);
  const invitedTeamMembers = useMemo(() => teamMembers.filter((member) => member.joined_via_invite && (!member.invited_by_user_id || member.invited_by_user_id === session?.user_id)), [session?.user_id, teamMembers]);

  const ownerNameForContent = (item: DraftItem) => {
    const member = item.created_by_user_id ? memberByUserId.get(item.created_by_user_id) : undefined;
    return member?.name || member?.email || item.created_by_user_id || "Unknown user";
  };

  const approveContent = async (item: DraftItem) => {
    if (!accessToken || item.status === "approved" || item.status === "published") return item;
    const response = await fetch(`/api/content/items/${item.id}/approve`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store"
    });
    if (!response.ok) throw new Error(await readError(response));
    const approved = (await response.json()) as DraftItem;
    setContentItems((current) => current.map((row) => (row.id === approved.id ? approved : row)));
    setReviewItem((current) => (current?.id === approved.id ? approved : current));
    return approved;
  };

  const scheduleContent = async (item: DraftItem, publishAt: Date, selectedRecurrence: Recurrence) => {
    if (!accessToken) return;
    const approved = await approveContent(item);
    const response = await fetch("/api/calendar/scheduled", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({
        content_id: approved.id,
        content_title: approved.title,
        publish_at: publishAt.toISOString(),
        timezone,
        recurrence: selectedRecurrence
      }),
      cache: "no-store"
    });
    if (!response.ok) throw new Error(await readError(response));
    return (await response.json()) as ScheduledPost;
  };

  const reviewContent = (item: DraftItem) => {
    setReviewItem(item);
    setNotice(null);
  };

  const scheduleReviewedContent = async () => {
    if (!reviewItem) return;
    const publishAt = new Date(`${scheduleDate}T${scheduleTime || "09:00"}:00`);
    if (Number.isNaN(publishAt.getTime())) {
      setNotice("Choose a valid date and time before scheduling.");
      return;
    }
    setIsActionBusy(true);
    setNotice(null);
    try {
      await scheduleContent(reviewItem, publishAt, recurrence);
      setNotice(`Scheduled ${reviewItem.title} for LinkedIn handoff.`);
      await loadDashboard();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Schedule failed.");
    } finally {
      setIsActionBusy(false);
    }
  };

  const publishNow = async (item: DraftItem) => {
    setIsActionBusy(true);
    setNotice(null);
    try {
      const publishAt = new Date(Date.now() + 30_000);
      await scheduleContent(item, publishAt, "none");
      setNotice(`Queued ${item.title} for LinkedIn publishing.`);
      await loadDashboard();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Publish now failed.");
    } finally {
      setIsActionBusy(false);
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Owner dashboard</h1>
          <p className="page-subtitle">Live account activity for {activeAccount?.name ?? "the active account"}.</p>
        </div>
        <div className="button-row">
          {lastUpdated ? <span className="status-badge neutral">Updated {lastUpdated}</span> : null}
          <button className="button secondary" type="button" onClick={() => void loadDashboard()} disabled={isLoading}>
            <RefreshCw size={15} aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="danger-note">{error}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <div className="metric-grid">
        <article className="metric-card">
          <Coins size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Credit balance</h3>
          <strong>{(balance ?? activeAccount?.credits ?? 0).toLocaleString()}</strong>
          <p>Synced from Credits Service.</p>
        </article>
        <article className="metric-card">
          <Zap size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>AI credits used</h3>
          <strong>{totalAiCreditsUsed.toLocaleString()}</strong>
          <p>{ledgerRows.length.toLocaleString()} generation charge{ledgerRows.length === 1 ? "" : "s"} recorded.</p>
        </article>
        <article className="metric-card">
          <Users size={22} color="var(--color-primary)" aria-hidden="true" />
          <h3>Total team members</h3>
          <strong>{activeTeamMembers.length.toLocaleString()}</strong>
          <p>Excludes the owner. {invitedTeamMembers.length.toLocaleString()} joined through your invite{invitedTeamMembers.length === 1 ? "" : "s"}; {activeCreators.toLocaleString()} active creator{activeCreators === 1 ? "" : "s"}.</p>
        </article>
      </div>

      <div className="admin-grid dashboard-panels with-top-gap">
        <article className="panel">
          <div className="panel-header"><h2>Recent credit purchases</h2><span className="status-badge neutral">{purchases.length} shown</span></div>
          {purchases.length ? (
            <table className="data-table">
              <thead><tr><th>Credits</th><th>Package</th><th>Date</th></tr></thead>
              <tbody>{purchases.map((item) => <tr key={item.id}><td className="mono">+{item.amount.toLocaleString()}</td><td>{String(item.metadata?.package_key ?? "Stripe checkout")}</td><td>{new Date(item.created_at).toLocaleString()}</td></tr>)}</tbody>
            </table>
          ) : <p>No credit purchases recorded yet.</p>}
        </article>

        <article className="panel">
          <div className="panel-header"><h2>Plan posture</h2><WalletCards size={22} color="var(--color-primary)" aria-hidden="true" /></div>
          <p>Manage credits, payment details, and account plan changes from one place.</p>
          <div className="button-row with-top-gap"><a className="button secondary" href="/credits">Manage credits <ArrowUpRight size={15} aria-hidden="true" /></a></div>
        </article>
      </div>

      <article className="panel with-top-gap">
        <div className="panel-header"><h2>Posts created by team members</h2><FileText size={20} color="var(--color-primary)" aria-hidden="true" /></div>
        {contentItems.length ? (
          <table className="data-table">
            <thead><tr><th>Post</th><th>Created by</th><th>Status</th><th>Prompt / work</th><th>Updated</th><th>Owner action</th></tr></thead>
            <tbody>
              {contentItems.slice(0, 30).map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.title}</strong><br /><span className="muted">{preview(item.body, 120)}</span></td>
                  <td>{ownerNameForContent(item)}</td>
                  <td><span className="status-badge neutral">{item.status ?? "draft"}</span></td>
                  <td>{preview(item.prompt, 100)}</td>
                  <td>{item.updated_at || item.created_at ? new Date(item.updated_at ?? item.created_at ?? "").toLocaleString() : "Unknown"}</td>
                  <td>
                    <div className="button-row compact">
                      <button className="button ghost" type="button" onClick={() => reviewContent(item)} disabled={isActionBusy}>Review</button>
                      <button className="button secondary" type="button" onClick={() => reviewContent(item)} disabled={isActionBusy}>
                        <CalendarClock size={14} aria-hidden="true" />
                        Schedule
                      </button>
                      <button className="button primary" type="button" onClick={() => void publishNow(item)} disabled={isActionBusy || item.status === "published"}>
                        <Send size={14} aria-hidden="true" />
                        Publish now
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state">No created posts found yet.</div>}
      </article>

      {reviewItem ? (
        <article className="panel with-top-gap">
          <div className="panel-header">
            <div>
              <h2>Review post</h2>
              <p className="muted">Created by {ownerNameForContent(reviewItem)} / status {reviewItem.status ?? "draft"}</p>
            </div>
            <button className="button ghost" type="button" onClick={() => setReviewItem(null)}>Close review</button>
          </div>
          <div className="review-post-body">
            <h3>{reviewItem.title}</h3>
            <p>{reviewItem.body}</p>
          </div>
          <div className="form-grid with-top-gap">
            <div className="field">
              <label htmlFor="owner-schedule-date">Date</label>
              <input id="owner-schedule-date" type="date" value={scheduleDate} onChange={(event) => setScheduleDate(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="owner-schedule-time">Time</label>
              <input id="owner-schedule-time" type="time" value={scheduleTime} onChange={(event) => setScheduleTime(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="owner-schedule-cadence">Cadence</label>
              <select id="owner-schedule-cadence" value={recurrence} onChange={(event) => setRecurrence(event.target.value as Recurrence)}>
                <option value="none">One time</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
          </div>
          <div className="button-row with-top-gap">
            <button className="button secondary" type="button" onClick={() => void approveContent(reviewItem).then(() => setNotice("Post approved."))} disabled={isActionBusy || reviewItem.status === "approved" || reviewItem.status === "published"}>
              <CheckCircle size={15} aria-hidden="true" />
              Approve only
            </button>
            <button className="button primary" type="button" onClick={() => void scheduleReviewedContent()} disabled={isActionBusy}>
              <CalendarClock size={15} aria-hidden="true" />
              Approve and schedule
            </button>
            <button className="button primary" type="button" onClick={() => void publishNow(reviewItem)} disabled={isActionBusy || reviewItem.status === "published"}>
              <Send size={15} aria-hidden="true" />
              Publish now to LinkedIn
            </button>
          </div>
        </article>
      ) : null}
    </section>
  );
}


