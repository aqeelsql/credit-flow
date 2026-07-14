"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Globe2, RefreshCw, Search, TimerReset } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

type Cadence = "once" | "daily" | "weekly" | "monthly";

type ScrapeSummary = {
  id: string;
  event_id?: string | null;
  target_url: string;
  domain?: string | null;
  job_type: string;
  status: string;
  created_at?: string | null;
  title?: string | null;
  summary?: string | null;
};

type ScrapeDocument = ScrapeSummary & {
  requested_by_user_id?: string | null;
  metadata?: Record<string, unknown> | null;
  raw?: {
    title?: string | null;
    markdown?: string | null;
    cleaned_html?: string | null;
    extracted_content?: string | null;
    links?: unknown;
    media?: unknown;
    metadata?: Record<string, unknown> | null;
    error_message?: string | null;
  } | null;
};

type ScrapeListResponse = { items: ScrapeSummary[] };
type RunNowResponse = { status: string; event_id: string; document_id: string; document: ScrapeDocument };

const cadenceSeconds: Record<Exclude<Cadence, "once">, number> = {
  daily: 86400,
  weekly: 604800,
  monthly: 2592000
};

function formatDate(value?: string | null) {
  if (!value) return "Pending";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

async function readError(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as { error?: string | { message?: string } } | null;
  const error = typeof body?.error === "string" ? body.error : body?.error?.message;
  return error || fallback;
}

function previewText(document: ScrapeDocument | null) {
  if (!document?.raw) return "Select a scraped document to preview extracted data.";
  const value = document.raw.markdown || document.raw.extracted_content || document.raw.cleaned_html;
  if (!value) return "No textual content was extracted.";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export function ScraperResearch() {
  const { activeAccount, accessToken } = useAuth();
  const [targetUrl, setTargetUrl] = useState("https://example.com");
  const [jobType, setJobType] = useState("competitor_check");
  const [cadence, setCadence] = useState<Cadence>("once");
  const [documents, setDocuments] = useState<ScrapeSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<ScrapeDocument | null>(null);
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);

  const selectedSummary = useMemo(() => documents.find((item) => item.id === selectedId), [documents, selectedId]);

  const loadDocuments = async () => {
    if (!activeAccount || !accessToken) {
      setDocuments([]);
      return;
    }
    setIsLoadingDocuments(true);
    try {
      const response = await fetch("/api/scraper/documents?limit=50", {
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: "no-store"
      });
      if (!response.ok) throw new Error(await readError(response, `Scraped documents failed to load (${response.status}).`));
      const data = (await response.json()) as ScrapeListResponse;
      setDocuments(data.items ?? []);
      setSelectedId((current) => current || data.items?.[0]?.id || null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Scraped documents failed to load.");
    } finally {
      setIsLoadingDocuments(false);
    }
  };

  useEffect(() => {
    void loadDocuments();
  }, [activeAccount?.id, accessToken]);

  useEffect(() => {
    const loadSelectedDocument = async () => {
      if (!selectedId || !accessToken) {
        setSelectedDocument(null);
        return;
      }
      try {
        const response = await fetch(`/api/scraper/documents/${selectedId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
          cache: "no-store"
        });
        if (!response.ok) throw new Error(await readError(response, `Scraped document failed to load (${response.status}).`));
        setSelectedDocument((await response.json()) as ScrapeDocument);
      } catch (error) {
        setSelectedDocument(null);
        setNotice(error instanceof Error ? error.message : "Scraped document failed to load.");
      }
    };
    void loadSelectedDocument();
  }, [selectedId, accessToken]);

  const submitScrape = async () => {
    if (!accessToken) {
      setNotice("You must be signed in before starting a scrape.");
      return;
    }
    setIsBusy(true);
    setNotice("");
    try {
      const body = {
        target_url: targetUrl,
        job_type: jobType,
        metadata: { source: "frontend", requested_from: "research_scraper" }
      };
      const response = await fetch(cadence === "once" ? "/api/scraper/scrapes/run-now" : "/api/scraper/recurring-scrapes", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify(cadence === "once" ? body : { ...body, interval_seconds: cadenceSeconds[cadence] })
      });
      if (!response.ok) throw new Error(await readError(response, `Scrape request failed (${response.status}).`));
      if (cadence === "once") {
        const result = (await response.json()) as RunNowResponse;
        setSelectedDocument(result.document);
        setSelectedId(result.document_id);
        setDocuments((current) => [
          {
            id: result.document_id,
            event_id: result.event_id,
            target_url: result.document.target_url,
            domain: result.document.domain,
            job_type: result.document.job_type,
            status: result.document.status,
            created_at: result.document.created_at,
            title: result.document.raw?.title || result.document.domain || result.document.target_url,
            summary: previewText(result.document).slice(0, 320)
          },
          ...current.filter((item) => item.id !== result.document_id)
        ]);
        setNotice(`Scrape completed. Event: ${result.event_id}.`);
      } else {
        const result = (await response.json()) as { id?: string; status?: string };
        setNotice(`Recurring scrape created. Job: ${result.id ?? "created"}. It will run on the ${cadence} cadence.`);
      }
      await loadDocuments();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Scrape request failed.");
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Research scraper</h1>
          <p className="page-subtitle">Run competitor and trend scrapes, then review the raw extracted documents stored in MongoDB.</p>
        </div>
        <span className="status-badge live">{documents.length} documents</span>
      </div>

      <div className="split-layout">
        <aside className="stack">
          <form
            className="panel form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              void submitScrape();
            }}
          >
            <Globe2 size={22} color="var(--color-primary)" aria-hidden="true" />
            <h2>Start scrape</h2>
            <div className="field">
              <label htmlFor="scrape-url">Target URL or domain</label>
              <input id="scrape-url" value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} placeholder="https://competitor.com/blog" />
            </div>
            <div className="field">
              <label htmlFor="job-type">Job type</label>
              <select id="job-type" value={jobType} onChange={(event) => setJobType(event.target.value)}>
                <option value="competitor_check">Competitor check</option>
                <option value="trend_scan">Trend scan</option>
                <option value="content_research">Content research</option>
                <option value="generic">Generic scrape</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="scrape-cadence">Cadence</label>
              <select id="scrape-cadence" value={cadence} onChange={(event) => setCadence(event.target.value as Cadence)}>
                <option value="once">Run once now</option>
                <option value="daily">Daily recurring</option>
                <option value="weekly">Weekly recurring</option>
                <option value="monthly">Monthly recurring</option>
              </select>
            </div>
            <button className="button primary" type="submit" disabled={isBusy || !targetUrl.trim()}>
              <Search size={16} aria-hidden="true" />
              {cadence === "once" ? "Scrape now" : "Create recurring scrape"}
            </button>
            <div className="notice">The worker respects robots.txt and per-domain rate limits before crawling.</div>
          </form>

          <article className="panel">
            <div className="panel-header">
              <h2>Recent results</h2>
              <button className="icon-button ghost" type="button" onClick={() => void loadDocuments()} disabled={isLoadingDocuments} aria-label="Refresh scraped documents">
                <RefreshCw size={16} aria-hidden="true" />
              </button>
            </div>
            <div className="draft-list">
              {isLoadingDocuments ? <div className="draft-item"><p>Loading scraped documents...</p></div> : null}
              {!isLoadingDocuments && documents.length === 0 ? <div className="draft-item"><p>No scraped documents yet.</p></div> : null}
              {documents.map((item) => (
                <div className={selectedId === item.id ? "draft-item selected" : "draft-item"} key={item.id}>
                  <button className="draft-select" type="button" onClick={() => setSelectedId(item.id)}>
                    <strong>{item.title || item.domain || item.target_url}</strong>
                    <p>{item.job_type} / {formatDate(item.created_at)}</p>
                  </button>
                </div>
              ))}
            </div>
          </article>
        </aside>

        <div className="stack">
          <article className="panel">
            <div className="panel-header">
              <div>
                <h2>{selectedSummary?.title || selectedSummary?.domain || "Scrape details"}</h2>
                {selectedSummary ? <p>{selectedSummary.target_url}</p> : null}
              </div>
              {selectedSummary ? <span className="status-badge success">{selectedSummary.status}</span> : <span className="status-badge neutral">Idle</span>}
            </div>
            {selectedSummary ? (
              <div className="metric-grid">
                <div className="metric-card"><span className="label">Job type</span><strong>{selectedSummary.job_type}</strong></div>
                <div className="metric-card"><span className="label">Domain</span><strong>{selectedSummary.domain || "Unknown"}</strong></div>
                <div className="metric-card"><span className="label">Stored</span><strong>{formatDate(selectedSummary.created_at)}</strong></div>
              </div>
            ) : null}
            {selectedSummary ? (
              <div className="button-row with-top-gap">
                <a className="button ghost" href={selectedSummary.target_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={16} aria-hidden="true" />
                  Open source
                </a>
                <button className="button secondary" type="button" onClick={() => void loadDocuments()} disabled={isLoadingDocuments}>
                  <TimerReset size={16} aria-hidden="true" />
                  Refresh status
                </button>
              </div>
            ) : null}
          </article>

          <article className="panel">
            <div className="panel-header">
              <h2>Extracted preview</h2>
              {selectedDocument?.event_id ? <span className="status-badge neutral">{selectedDocument.event_id}</span> : null}
            </div>
            <pre className="stream-output mono">{previewText(selectedDocument).slice(0, 6000)}</pre>
          </article>

          {selectedDocument?.raw ? (
            <article className="panel">
              <div className="panel-header"><h2>Raw metadata</h2></div>
              <pre className="stream-output mono">{JSON.stringify({ metadata: selectedDocument.raw.metadata, links: selectedDocument.raw.links, media: selectedDocument.raw.media }, null, 2)}</pre>
            </article>
          ) : null}
        </div>
      </div>

      {notice ? <div className="notice with-top-gap">{notice}</div> : null}
    </section>
  );
}
