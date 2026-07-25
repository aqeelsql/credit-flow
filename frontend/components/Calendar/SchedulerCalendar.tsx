"use client";

import { useEffect, useMemo, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import timeGridPlugin from "@fullcalendar/timegrid";
import type { EventInput } from "@fullcalendar/core";
import { CalendarPlus, Repeat, Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog/ConfirmDialog";
import { useAuth } from "@/lib/auth-context";

type DraftContent = {
  id: string;
  title: string;
  body: string;
  status?: string;
  image_url?: string | null;
  image_asset_ref?: string | null;
  metadata?: { has_image?: boolean } | null;
};

type ScheduledPost = {
  id: string;
  content_id: string;
  content_title: string;
  publish_at: string;
  publish_at_local?: string | null;
  timezone: string;
  recurrence: Recurrence;
  status: string;
};

type Recurrence = "none" | "daily" | "weekly" | "monthly";

type DraftListResponse = { items: DraftContent[] };
type ScheduledListResponse = { items: ScheduledPost[] };

const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const SCHEDULE_CONTENT_HANDOFF_KEY = "creditflow:schedule-content-handoff";

function calendarRange() {
  const start = new Date();
  start.setMonth(start.getMonth() - 2, 1);
  start.setHours(0, 0, 0, 0);
  const end = new Date();
  end.setMonth(end.getMonth() + 3, 1);
  end.setHours(0, 0, 0, 0);
  return { start: start.toISOString(), end: end.toISOString() };
}

function dateClickToPublishAt(date: Date, allDay: boolean) {
  const next = new Date(date);
  if (allDay) next.setHours(9, 0, 0, 0);
  return next.toISOString();
}

function draftHasImage(draft: DraftContent) {
  return Boolean(draft.image_url || draft.image_asset_ref || draft.metadata?.has_image);
}

function cadenceLabel(value: Recurrence) {
  if (value === "daily") return "Daily";
  if (value === "weekly") return "Weekly";
  if (value === "monthly") return "Monthly";
  return "One time";
}

function formatScheduleDate(value?: string | null) {
  if (!value) return "Not scheduled";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function toDateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function toTimeInputValue(value: Date) {
  return `${String(value.getHours()).padStart(2, "0")}:${String(value.getMinutes()).padStart(2, "0")}`;
}

function defaultScheduleDate() {
  const next = new Date();
  next.setDate(next.getDate() + 1);
  next.setHours(9, 0, 0, 0);
  return next;
}

async function readError(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as { error?: string | { message?: string } } | null;
  const error = typeof body?.error === "string" ? body.error : body?.error?.message;
  return error || fallback;
}

export function SchedulerCalendar() {
  const { activeAccount, accessToken } = useAuth();
  const [drafts, setDrafts] = useState<DraftContent[]>([]);
  const [events, setEvents] = useState<ScheduledPost[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState("");
  const [recurring, setRecurring] = useState<Recurrence>("none");
  const [scheduleDate, setScheduleDate] = useState(() => toDateInputValue(defaultScheduleDate()));
  const [scheduleTime, setScheduleTime] = useState(() => toTimeInputValue(defaultScheduleDate()));
  const [pendingCancel, setPendingCancel] = useState<ScheduledPost | null>(null);
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const loadDrafts = async () => {
    if (!activeAccount || !accessToken) return;
    const [draftResponse, approvedResponse] = await Promise.all([
      fetch("/api/content/drafts?limit=100", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }),
      fetch("/api/content/drafts?status=approved&limit=100", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" })
    ]);
    if (!draftResponse.ok) throw new Error(await readError(draftResponse, `Drafts failed to load (${draftResponse.status}).`));
    const draftsData = (await draftResponse.json()) as DraftListResponse;
    const approvedData = approvedResponse.ok ? ((await approvedResponse.json()) as DraftListResponse) : { items: [] };
    let merged = [...(draftsData.items ?? []), ...(approvedData.items ?? [])].filter((draft, index, items) => items.findIndex((item) => item.id === draft.id) === index);
    let handoffContentId = "";
    try {
      const raw = window.sessionStorage.getItem(SCHEDULE_CONTENT_HANDOFF_KEY);
      if (raw) {
        const payload = JSON.parse(raw) as Partial<DraftContent> & { contentId?: string };
        handoffContentId = payload.contentId ?? payload.id ?? "";
        if (handoffContentId && !merged.some((draft) => draft.id === handoffContentId)) {
          merged = [
            {
              id: handoffContentId,
              title: payload.title || "Untitled post",
              body: payload.body || "",
              status: payload.status || "draft",
              image_url: payload.image_url ?? null,
              image_asset_ref: payload.image_asset_ref ?? null,
              metadata: payload.metadata ?? null
            },
            ...merged
          ];
        }
        window.sessionStorage.removeItem(SCHEDULE_CONTENT_HANDOFF_KEY);
      }
    } catch {
      window.sessionStorage.removeItem(SCHEDULE_CONTENT_HANDOFF_KEY);
    }
    setDrafts(merged);
    setSelectedDraftId((current) => {
      if (handoffContentId && merged.some((draft) => draft.id === handoffContentId)) return handoffContentId;
      if (current && merged.some((draft) => draft.id === current)) return current;
      return merged[0]?.id || "";
    });
  };

  const loadScheduled = async () => {
    if (!activeAccount || !accessToken) return;
    const { start, end } = calendarRange();
    const url = `/api/calendar/scheduled?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&timezone=${encodeURIComponent(timezone)}`;
    const response = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response, `Calendar failed to load (${response.status}).`));
    const data = (await response.json()) as ScheduledListResponse;
    setEvents(data.items ?? []);
  };

  const reload = async () => {
    setIsBusy(true);
    try {
      await Promise.all([loadDrafts(), loadScheduled()]);
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Calendar failed to load.");
    } finally {
      setIsBusy(false);
    }
  };

  useEffect(() => {
    void reload();
  }, [activeAccount?.id, accessToken]);

  const calendarEvents = useMemo<EventInput[]>(
    () =>
      events
        .filter((event) => event.status !== "cancelled")
        .map((event) => ({
          id: event.id,
          title: `${event.content_title}${event.recurrence === "weekly" ? " / weekly" : ""}`,
          start: event.publish_at_local ?? event.publish_at,
          extendedProps: { recurrence: event.recurrence, status: event.status }
        })),
    [events]
  );

  const activeScheduledContentIds = useMemo(
    () => new Set(events.filter((event) => event.status === "scheduled").map((event) => event.content_id)),
    [events]
  );
  const availableDrafts = useMemo(
    () => drafts.filter((draft) => !activeScheduledContentIds.has(draft.id)),
    [drafts, activeScheduledContentIds]
  );
  const selectedDraft = availableDrafts.find((draft) => draft.id === selectedDraftId);

  useEffect(() => {
    if (selectedDraftId && !availableDrafts.some((draft) => draft.id === selectedDraftId)) {
      setSelectedDraftId(availableDrafts[0]?.id || "");
      return;
    }
    if (!selectedDraftId && availableDrafts.length > 0) {
      setSelectedDraftId(availableDrafts[0].id);
    }
  }, [availableDrafts, selectedDraftId]);

  const scheduleDraft = async (date: Date, allDay: boolean) => {
    if (!selectedDraft || !accessToken) return;
    setIsBusy(true);
    try {
      const response = await fetch("/api/calendar/scheduled", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ content_id: selectedDraft.id, content_title: selectedDraft.title, publish_at: dateClickToPublishAt(date, allDay), timezone, recurrence: recurring })
      });
      if (!response.ok) throw new Error(await readError(response, `Schedule failed (${response.status}).`));
      const created = (await response.json()) as ScheduledPost;
      setEvents((current) => [...current.filter((event) => event.content_id !== created.content_id || event.status !== "scheduled"), created]);
      setDrafts((current) => current.filter((draft) => draft.id !== created.content_id));
      setSelectedDraftId("");
      setNotice("Post scheduled.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Schedule failed.");
    } finally {
      setIsBusy(false);
    }
  };

  const scheduleSelectedDraft = async () => {
    if (!selectedDraft || !accessToken) return;
    const publishAt = new Date(`${scheduleDate}T${scheduleTime || "09:00"}:00`);
    if (Number.isNaN(publishAt.getTime())) {
      setNotice("Choose a valid date and time.");
      return;
    }
    setIsBusy(true);
    try {
      const response = await fetch("/api/calendar/scheduled", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ content_id: selectedDraft.id, content_title: selectedDraft.title, publish_at: publishAt.toISOString(), timezone, recurrence: recurring })
      });
      if (!response.ok) throw new Error(await readError(response, `Schedule failed (${response.status}).`));
      const saved = (await response.json()) as ScheduledPost;
      setEvents((current) => [...current.filter((event) => event.id !== saved.id && (event.content_id !== saved.content_id || event.status !== "scheduled")), saved]);
      setDrafts((current) => current.filter((draft) => draft.id !== saved.content_id));
      setSelectedDraftId("");
      setNotice("Post scheduled.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Schedule failed.");
    } finally {
      setIsBusy(false);
    }
  };

  const reschedule = async (scheduledId: string, date: Date | null) => {
    if (!date || !accessToken) return;
    const existing = events.find((event) => event.id === scheduledId);
    try {
      const response = await fetch(`/api/calendar/scheduled/${scheduledId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ publish_at: date.toISOString(), timezone, recurrence: existing?.recurrence ?? "none" })
      });
      if (!response.ok) throw new Error(await readError(response, `Reschedule failed (${response.status}).`));
      const updated = (await response.json()) as ScheduledPost;
      setEvents((current) => current.map((event) => (event.id === updated.id ? updated : event)));
      setNotice("Post rescheduled.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Reschedule failed.");
      void loadScheduled();
    }
  };

  const cancelScheduled = async () => {
    if (!pendingCancel || !accessToken) return;
    try {
      const response = await fetch(`/api/calendar/scheduled/${pendingCancel.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${accessToken}` } });
      if (!response.ok) throw new Error(await readError(response, `Cancel failed (${response.status}).`));
      setEvents((current) => current.filter((event) => event.id !== pendingCancel.id));
      setNotice("Scheduled post cancelled.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Cancel failed.");
    } finally {
      setPendingCancel(null);
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Calendar and scheduler</h1>
          <p className="page-subtitle">Place drafts on the calendar, reschedule with drag-and-drop, or cancel a post.</p>
        </div>
        <span className="status-badge live">{calendarEvents.length} scheduled</span>
      </div>

      <div className="calendar-layout">
        <aside className="panel form-grid">
          <CalendarPlus size={22} color="var(--color-primary)" aria-hidden="true" />
          <h2>Schedule draft</h2>
          <div className="field">
            <label htmlFor="draft-select">Draft</label>
            <select id="draft-select" value={selectedDraftId} onChange={(event) => setSelectedDraftId(event.target.value)}>
              {availableDrafts.length === 0 ? <option value="">No unscheduled drafts</option> : null}
              {availableDrafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.title}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="recurring-select">Cadence</label>
            <select id="recurring-select" value={recurring} onChange={(event) => setRecurring(event.target.value as Recurrence)}>
              <option value="none">One time</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="schedule-date">Date</label>
            <input id="schedule-date" type="date" value={scheduleDate} onChange={(event) => setScheduleDate(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="schedule-time">Time</label>
            <input id="schedule-time" type="time" value={scheduleTime} onChange={(event) => setScheduleTime(event.target.value)} />
          </div>
          <button className="button primary" type="button" onClick={() => void scheduleSelectedDraft()} disabled={!selectedDraft || isBusy}>
            Schedule selected post
          </button>
          <button className="button ghost" type="button" onClick={() => void reload()} disabled={isBusy}>Refresh</button>
          {selectedDraft ? (
            <div className="schedule-item">
              <strong>{selectedDraft.title}</strong>
              <p>{draftHasImage(selectedDraft) ? "Text and image post" : "Text-only post"}{selectedDraft.status === "approved" ? " / Approved" : ""}</p>
              <p>Status: Not scheduled</p>
              <p>Date/time: <span className="mono">{formatScheduleDate(`${scheduleDate}T${scheduleTime || "09:00"}:00`)}</span></p>
              <p>Cadence: {cadenceLabel(recurring)}</p>
            </div>
          ) : null}
        </aside>

        <div className="calendar-shell">
          <FullCalendar
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            headerToolbar={{ left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek" }}
            events={calendarEvents}
            editable
            selectable
            height="auto"
            dateClick={(info) => void scheduleDraft(info.date, info.allDay)}
            eventDrop={(info) => void reschedule(info.event.id, info.event.start)}
            eventClick={(info) => {
              const event = events.find((item) => item.id === info.event.id);
              if (event) setPendingCancel(event);
            }}
          />
        </div>
      </div>

      {notice ? <div className="notice">{notice}</div> : null}

      <article className="panel">
        <div className="panel-header"><h2>Upcoming posts</h2><Repeat size={20} color="var(--color-primary)" aria-hidden="true" /></div>
        <div className="schedule-list">
          {events.filter((event) => event.status !== "cancelled").map((event) => (
            <div className="schedule-item" key={event.id}>
              <div className="item-header">
                <strong>{event.content_title}</strong>
                <button className="icon-button danger" type="button" aria-label={`Cancel ${event.content_title}`} onClick={() => setPendingCancel(event)}><Trash2 size={16} aria-hidden="true" /></button>
              </div>
              <p><span className="mono">{event.publish_at_local ?? event.publish_at}</span> / {event.recurrence === "weekly" ? "weekly" : "one time"}</p>
            </div>
          ))}
        </div>
      </article>

      <ConfirmDialog open={!!pendingCancel} title="Cancel scheduled post" message={`Cancel ${pendingCancel?.content_title ?? "this scheduled post"}?`} confirmLabel="Cancel post" onCancel={() => setPendingCancel(null)} onConfirm={() => void cancelScheduled()} />
    </section>
  );
}

