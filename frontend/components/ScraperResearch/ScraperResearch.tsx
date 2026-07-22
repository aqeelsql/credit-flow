"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, FileText, Globe2, RefreshCw, Search, Sparkles, TimerReset } from "lucide-react";
import { useRouter } from "next/navigation";
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
    markdown?: unknown;
    cleaned_html?: unknown;
    extracted_content?: unknown;
    links?: unknown;
    media?: unknown;
    metadata?: Record<string, unknown> | null;
    error_message?: string | null;
  } | null;
};

type ResearchSource = {
  status: string;
  title?: string | null;
  url: string;
  snippet?: string | null;
  content?: string | null;
  excerpt?: string | null;
  word_count?: number | null;
  document_id?: string | null;
  error_reason?: string | null;
  raw?: ScrapeDocument["raw"];
};

type ResearchPackSummary = {
  id: string;
  topic: string;
  job_type: string;
  output_type: string;
  status: string;
  created_at?: string | null;
  source_count: number;
  successful_source_count: number;
  summary?: string | null;
  content_draft_id?: string | null;
};

type ResearchPack = ResearchPackSummary & {
  key_points?: string[];
  research_brief?: string | null;
  sources?: ResearchSource[];
  generated_post?: string;
  content_draft?: { id?: string; title?: string; status?: string } | null;
};

type ResearchJob = {
  id: string;
  topic: string;
  cadence: Cadence;
  job_type: string;
  output_type: string;
  max_sources: number;
  enabled: boolean;
  next_run_at?: string | null;
  auto_generate_post?: boolean;
};

type ScrapeListResponse = { items: ScrapeSummary[] };
type RunNowResponse = { status: string; event_id: string; document_id: string; document: ScrapeDocument };
type ResearchPackListResponse = { items: ResearchPackSummary[] };
type ResearchJobListResponse = { items: ResearchJob[] };
type TopicResearchResponse = { status: string; research_pack_id: string; pack: ResearchPack };
type ContentDraft = { id: string; title: string; status?: string };

const SCRAPER_PROMPT_HANDOFF_KEY = "creditflow:scraper-prompt-handoff";
const DEFAULT_OUTPUT_TYPE = "linkedin_post";

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

function stringifyValue(value: unknown) {
  if (!value) return "";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function previewText(document: ScrapeDocument | null) {
  if (!document?.raw) return "Select a scraped document to preview extracted data.";
  return stringifyValue(document.raw.extracted_content || document.raw.markdown || document.raw.cleaned_html) || "No textual content was extracted.";
}

function compactUrlGenerationBrief(document: ScrapeDocument) {
  const title = document.raw?.title || document.title || document.domain || document.target_url;
  const rawText = previewText(document);
  const usableText = rawText
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter((line) => line.length >= 35)
    .filter((line, index, lines) => lines.indexOf(line) === index)
    .filter((line) => !/(accept cookies|privacy policy|terms of use|all rights reserved|subscribe|sign up|advertisement)/i.test(line))
    .slice(0, 18)
    .join("\n");
  return `Title: ${title}\nSource: ${document.target_url}\nDomain: ${document.domain || "unknown"}\n\nUseful scraped page data:\n${clipText(usableText || rawText, 4500)}`;
}

function researchPreview(pack: ResearchPack | null) {
  if (!pack) return "Run or select a research pack to preview topic-based scraped data.";
  const points = pack.key_points?.length ? pack.key_points.map((point) => `- ${point}`).join("\n") : "No key points extracted yet.";
  const completed = (pack.sources ?? []).filter((source) => source.status === "completed");
  const skipped = (pack.sources ?? []).filter((source) => source.status !== "completed");
  const marketData = completed.map((source, index) => {
    const body = source.content || source.excerpt || stringifyValue(source.raw?.markdown || source.raw?.extracted_content || source.snippet);
    return `${index + 1}. ${source.title || source.url}\nSource: ${source.url}\nWords scraped: ${source.word_count ?? "unknown"}\n\n${body}`;
  }).join("\n\n---\n\n");
  const skippedText = skipped.length ? `\n\nSkipped or blocked sources:\n${skipped.map((source) => `- ${source.title || source.url}: ${source.error_reason || source.status}`).join("\n")}` : "";
  return `Topic: ${pack.topic}\n\nKey points from scraped market data:\n${points}\n\nScraped market data:\n${marketData || "No meaningful article/body text was extracted. Try a more specific topic or fewer sources."}${skippedText}`;
}

function clipText(value: string, maxLength: number) {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized;
}

function researchGenerationBrief(pack: ResearchPack) {
  if (pack.research_brief) {
    return clipText(pack.research_brief, 6000);
  }
  const points = (pack.key_points ?? []).map((point) => `- ${clipText(point, 360)}`).join("\n");
  const completed = (pack.sources ?? []).filter((source) => source.status === "completed").slice(0, 4);
  const sourceBriefs = completed.map((source, index) => {
    const body = clipText(source.content || source.excerpt || stringifyValue(source.raw?.markdown || source.raw?.extracted_content || source.snippet), 900);
    return `${index + 1}. ${source.title || source.url}\nSource: ${source.url}\nUseful scraped data: ${body}`;
  }).join("\n\n");
  return `Topic: ${pack.topic}\n\nKey facts:\n${points || "Use the scraped source data below."}\n\nScraped source data:\n${sourceBriefs || "No usable scraped source text was available."}`;
}

export function ScraperResearch() {
  const router = useRouter();
  const { activeAccount, accessToken } = useAuth();
  const [scrapeMode, setScrapeMode] = useState<"topic" | "url">("topic");
  const [targetUrl, setTargetUrl] = useState("https://example.com");
  const [jobType, setJobType] = useState("competitor_check");
  const [cadence, setCadence] = useState<Cadence>("once");
  const [topic, setTopic] = useState("Latest stock market news for fintech founders");
  const [maxSources, setMaxSources] = useState(5);
  const [autoGeneratePost, setAutoGeneratePost] = useState(false);
  const [documents, setDocuments] = useState<ScrapeSummary[]>([]);
  const [researchPacks, setResearchPacks] = useState<ResearchPackSummary[]>([]);
  const [researchJobs, setResearchJobs] = useState<ResearchJob[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<ScrapeDocument | null>(null);
  const [selectedPackId, setSelectedPackId] = useState<string | null>(null);
  const [selectedPack, setSelectedPack] = useState<ResearchPack | null>(null);
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [isLoadingResearch, setIsLoadingResearch] = useState(false);
  const [showSavedScrapedData, setShowSavedScrapedData] = useState(false);

  const selectedSummary = useMemo(() => documents.find((item) => item.id === selectedId), [documents, selectedId]);

  const authHeaders = () => ({ Authorization: `Bearer ${accessToken}` });

  const loadDocuments = async () => {
    if (!activeAccount || !accessToken) {
      setDocuments([]);
      return;
    }
    setIsLoadingDocuments(true);
    try {
      const response = await fetch("/api/scraper/documents?limit=50", { headers: authHeaders(), cache: "no-store" });
      if (!response.ok) throw new Error(await readError(response, `Scraped documents failed to load (${response.status}).`));
      const data = (await response.json()) as ScrapeListResponse;
      setDocuments(data.items ?? []);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Scraped documents failed to load.");
    } finally {
      setIsLoadingDocuments(false);
    }
  };

  const loadResearch = async () => {
    if (!activeAccount || !accessToken) {
      setResearchPacks([]);
      setResearchJobs([]);
      return;
    }
    setIsLoadingResearch(true);
    try {
      const [packsResponse, jobsResponse] = await Promise.all([
        fetch("/api/scraper/research-packs?limit=50", { headers: authHeaders(), cache: "no-store" }),
        fetch("/api/scraper/research-jobs?limit=50", { headers: authHeaders(), cache: "no-store" })
      ]);
      if (!packsResponse.ok) throw new Error(await readError(packsResponse, `Research packs failed to load (${packsResponse.status}).`));
      if (!jobsResponse.ok) throw new Error(await readError(jobsResponse, `Research jobs failed to load (${jobsResponse.status}).`));
      const packs = (await packsResponse.json()) as ResearchPackListResponse;
      const jobs = (await jobsResponse.json()) as ResearchJobListResponse;
      setResearchPacks(packs.items ?? []);
      setResearchJobs(jobs.items ?? []);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Research failed to load.");
    } finally {
      setIsLoadingResearch(false);
    }
  };

  useEffect(() => {
    void loadDocuments();
    void loadResearch();
  }, [activeAccount?.id, accessToken]);

  useEffect(() => {
    const loadSelectedDocument = async () => {
      if (!selectedId || !accessToken) {
        setSelectedDocument(null);
        return;
      }
      try {
        const response = await fetch(`/api/scraper/documents/${selectedId}`, { headers: authHeaders(), cache: "no-store" });
        if (!response.ok) throw new Error(await readError(response, `Scraped document failed to load (${response.status}).`));
        setSelectedDocument((await response.json()) as ScrapeDocument);
      } catch (error) {
        setSelectedDocument(null);
        setNotice(error instanceof Error ? error.message : "Scraped document failed to load.");
      }
    };
    void loadSelectedDocument();
  }, [selectedId, accessToken]);

  useEffect(() => {
    const loadSelectedPack = async () => {
      if (!selectedPackId || !accessToken) {
        setSelectedPack(null);
        return;
      }
      try {
        const response = await fetch(`/api/scraper/research-packs/${selectedPackId}`, { headers: authHeaders(), cache: "no-store" });
        if (!response.ok) throw new Error(await readError(response, `Research pack failed to load (${response.status}).`));
        const pack = (await response.json()) as ResearchPack;
        setSelectedPack(pack);
      } catch (error) {
        setSelectedPack(null);
        setNotice(error instanceof Error ? error.message : "Research pack failed to load.");
      }
    };
    void loadSelectedPack();
  }, [selectedPackId, accessToken]);

  const submitScrape = async () => {
    if (!accessToken) {
      setNotice("You must be signed in before starting a scrape.");
      return;
    }
    setIsBusy(true);
    setNotice("");
    try {
      const body = { target_url: targetUrl, job_type: jobType, metadata: { source: "frontend", requested_from: "research_scraper" } };
      const response = await fetch("/api/scraper/scrapes/run-now", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(body)
      });
      if (!response.ok) throw new Error(await readError(response, `Scrape request failed (${response.status}).`));
      const result = (await response.json()) as RunNowResponse;
      setSelectedPack(null);
      setSelectedPackId(null);
      setSelectedDocument(result.document);
      setSelectedId(result.document_id);
      setDocuments((current) => [{ id: result.document_id, event_id: result.event_id, target_url: result.document.target_url, domain: result.document.domain, job_type: result.document.job_type, status: result.document.status, created_at: result.document.created_at, title: result.document.raw?.title || result.document.domain || result.document.target_url, summary: previewText(result.document).slice(0, 320) }, ...current.filter((item) => item.id !== result.document_id)]);
      if (cadence !== "once") {
        const recurringResponse = await fetch("/api/scraper/recurring-scrapes", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ ...body, interval_seconds: cadenceSeconds[cadence] })
        });
        if (!recurringResponse.ok) throw new Error(await readError(recurringResponse, `Recurring scrape failed to save (${recurringResponse.status}).`));
        const recurring = (await recurringResponse.json()) as { id?: string };
        setNotice(`Scrape completed and recurring URL scrape saved. Job: ${recurring.id ?? "created"}. Event: ${result.event_id}.`);
      } else {
        setNotice(`Scrape completed. Event: ${result.event_id}.`);
      }
      await loadDocuments();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Scrape request failed.");
    } finally {
      setIsBusy(false);
    }
  };

  const runTopicResearch = async () => {
    if (!accessToken) return;
    setIsBusy(true);
    setNotice("");
    try {
      const response = await fetch("/api/scraper/research/run-now", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ topic, job_type: "topic_research", output_type: DEFAULT_OUTPUT_TYPE, max_sources: maxSources, metadata: { source: "frontend" } })
      });
      if (!response.ok) throw new Error(await readError(response, `Topic research failed (${response.status}).`));
      const result = (await response.json()) as TopicResearchResponse;
      setSelectedDocument(null);
      setSelectedId(null);
      setSelectedPack(result.pack);
      setSelectedPackId(result.research_pack_id);
      setResearchPacks((current) => [{ id: result.research_pack_id, topic: result.pack.topic, job_type: result.pack.job_type, output_type: result.pack.output_type, status: result.pack.status, created_at: result.pack.created_at, source_count: result.pack.sources?.length ?? 0, successful_source_count: result.pack.sources?.filter((source) => source.status === "completed").length ?? 0, summary: result.pack.key_points?.join("\n") }, ...current.filter((item) => item.id !== result.research_pack_id)]);
      setNotice("Topic research completed and saved as a research pack.");
      await loadResearch();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Topic research failed.");
    } finally {
      setIsBusy(false);
    }
  };

  const saveResearchJob = async () => {
    if (!accessToken) return;
    setIsBusy(true);
    setNotice("");
    try {
      const response = await fetch("/api/scraper/research-jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ topic, cadence, job_type: "topic_research", output_type: DEFAULT_OUTPUT_TYPE, max_sources: maxSources, auto_generate_post: autoGeneratePost, metadata: { source: "frontend" } })
      });
      if (!response.ok) throw new Error(await readError(response, `Research draft failed to save (${response.status}).`));
      const result = (await response.json()) as { id: string };
      setNotice(`Research draft saved. It will run ${cadence}. Job: ${result.id}.`);
      await loadResearch();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Research draft failed to save.");
    } finally {
      setIsBusy(false);
    }
  };

  const submitConfiguredScrape = async () => {
    if (scrapeMode === "url") {
      await submitScrape();
      return;
    }
    if (cadence === "once") {
      await runTopicResearch();
      return;
    }
    await runTopicResearch();
    await saveResearchJob();
  };

  const closeResearchPreview = () => {
    setSelectedPack(null);
    setSelectedPackId(null);
  };

  const closeUrlPreview = () => {
    setSelectedDocument(null);
    setSelectedId(null);
  };

  const selectResearchPack = (packId: string) => {
    setSelectedId(null);
    setSelectedDocument(null);
    setSelectedPackId(packId);
    setShowSavedScrapedData(false);
  };

  const selectUrlDocument = (documentId: string) => {
    setSelectedPackId(null);
    setSelectedPack(null);
    setSelectedId(documentId);
    setShowSavedScrapedData(false);
  };

  const openSavedScrapedData = () => {
    setShowSavedScrapedData(true);
    void loadResearch();
    void loadDocuments();
  };

  const saveContentDraft = async (title: string, body: string, promptText: string, metadata: Record<string, unknown>) => {
    if (!activeAccount || !accessToken) {
      setNotice("You must be signed in before saving scraped data as a draft.");
      return null;
    }
    const response = await fetch("/api/content/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ title, body, prompt: promptText, metadata })
    });
    if (!response.ok) {
      throw new Error(await readError(response, `Draft save failed (${response.status}).`));
    }
    return (await response.json()) as ContentDraft;
  };

  const saveResearchDataDraft = async () => {
    if (!selectedPack) {
      setNotice("Select a research pack first.");
      return;
    }
    setIsBusy(true);
    setNotice("");
    try {
      const draft = await saveContentDraft(
        `Scraped research: ${selectedPack.topic}`.slice(0, 180),
        researchPreview(selectedPack),
        selectedPack.topic,
        { source: "scraper_research_data", research_pack_id: selectedPack.id, topic: selectedPack.topic }
      );
      if (draft?.id) {
        setSelectedPack((current) => current ? { ...current, content_draft_id: draft.id } : current);
        setResearchPacks((current) => current.map((pack) => pack.id === selectedPack.id ? { ...pack, content_draft_id: draft.id } : pack));
      }
      setNotice(`Scraped research saved as draft${draft?.id ? ` (${draft.id})` : ""}. Open Content Studio to see it in Drafts.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Scraped research draft save failed.");
    } finally {
      setIsBusy(false);
    }
  };

  const saveUrlDataDraft = async () => {
    if (!selectedDocument) {
      setNotice("Select a scraped URL result first.");
      return;
    }
    setIsBusy(true);
    setNotice("");
    try {
      const title = selectedDocument.raw?.title || selectedDocument.domain || selectedDocument.target_url;
      const draft = await saveContentDraft(
        `Scraped data: ${title}`.slice(0, 180),
        previewText(selectedDocument),
        `Raw scraped data from ${selectedDocument.target_url}`,
        { source: "scraper_url_data", scraped_document_id: selectedDocument.id, target_url: selectedDocument.target_url }
      );
      setNotice(`Scraped URL data saved as draft${draft?.id ? ` (${draft.id})` : ""}. Open Content Studio to see it in Drafts.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Scraped URL draft save failed.");
    } finally {
      setIsBusy(false);
    }
  };

  const sendResearchToContentStudio = () => {
    if (!selectedPack) {
      setNotice("Select a research pack first.");
      return;
    }
    const prompt = `Write a professional ${selectedPack.output_type?.replaceAll("_", " ") || "LinkedIn post"} using the scraped research brief below. Do not invent facts. Make it useful, polished, and suitable for social media.\n\n${researchGenerationBrief(selectedPack)}`;
    window.sessionStorage.setItem(SCRAPER_PROMPT_HANDOFF_KEY, JSON.stringify({ prompt, autoGenerate: true }));
    router.push("/content-studio");
  };

  const sendUrlToContentStudio = () => {
    if (!selectedDocument) {
      setNotice("Select a scraped URL result first.");
      return;
    }
    const prompt = `Write a professional social media post using the scraped webpage brief below. Do not invent facts. Make it useful, polished, and suitable for social media.\n\n${compactUrlGenerationBrief(selectedDocument)}`;
    window.sessionStorage.setItem(SCRAPER_PROMPT_HANDOFF_KEY, JSON.stringify({ prompt, autoGenerate: true }));
    router.push("/content-studio");
  };

  const selectedPreviewTitle = selectedPack?.topic || selectedDocument?.raw?.title || selectedDocument?.title || selectedDocument?.domain || "Scraped data preview";
  const selectedPreviewBody = selectedPack ? researchPreview(selectedPack) : previewText(selectedDocument);
  const selectedPreviewKind = selectedPack ? "Topic research" : selectedDocument ? "URL scrape" : "Idle";

  const generateSelectedPost = () => {
    if (selectedPack) {
      sendResearchToContentStudio();
      return;
    }
    if (selectedDocument) {
      sendUrlToContentStudio();
      return;
    }
    setNotice("Select scraped data first.");
  };

  const deleteSelectedScrapedData = async () => {
    if (!accessToken) return;
    const packId = selectedPack?.id;
    const documentId = selectedDocument?.id || selectedId;
    if (!packId && !documentId) {
      setNotice("Select scraped data first.");
      return;
    }
    setIsBusy(true);
    setNotice("");
    try {
      const url = packId ? `/api/scraper/research-packs/${packId}` : `/api/scraper/documents/${documentId}`;
      const response = await fetch(url, { method: "DELETE", headers: authHeaders() });
      if (!response.ok) throw new Error(await readError(response, `Delete failed (${response.status}).`));
      if (packId) {
        setResearchPacks((current) => current.filter((pack) => pack.id !== packId));
        closeResearchPreview();
      } else if (documentId) {
        setDocuments((current) => current.filter((doc) => doc.id !== documentId));
        closeUrlPreview();
      }
      setNotice("Scraped data deleted.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Delete failed.");
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Research scraper</h1>
          <p className="page-subtitle">Create recurring topic research, scrape discovered sources, and turn research packs into Content Studio drafts.</p>
        </div>
        <span className="status-badge live">{researchPacks.length} research packs</span>
      </div>

      <div className="split-layout">
        <aside className="stack">
          <form className="panel form-grid" onSubmit={(event) => { event.preventDefault(); void submitConfiguredScrape(); }}>
            {scrapeMode === "topic" ? <FileText size={22} color="var(--color-primary)" aria-hidden="true" /> : <Globe2 size={22} color="var(--color-primary)" aria-hidden="true" />}
            <h2>Configure scraper</h2>
            <div className="field"><label htmlFor="scrape-mode">Research mode</label><select id="scrape-mode" value={scrapeMode} onChange={(event) => setScrapeMode(event.target.value as "topic" | "url")}><option value="topic">Topic research</option><option value="url">Scrape from URL</option></select></div>
            {scrapeMode === "topic" ? <>
              <div className="field"><label htmlFor="research-topic">What should we research?</label><textarea id="research-topic" value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Latest stock market news for fintech founders" /></div>
              <div className="field"><label htmlFor="max-sources">Sources per run</label><input id="max-sources" type="number" min={1} max={10} value={maxSources} onChange={(event) => setMaxSources(Number(event.target.value))} /></div>
              {cadence !== "once" ? <label className="check-row"><input type="checkbox" checked={autoGeneratePost} onChange={(event) => setAutoGeneratePost(event.target.checked)} /><span>Auto-generate post after scheduled runs</span></label> : null}
            </> : <>
              <div className="field"><label htmlFor="scrape-url">Target URL or domain</label><input id="scrape-url" value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} placeholder="https://competitor.com/blog" /></div>
              <div className="field"><label htmlFor="job-type">Job type</label><select id="job-type" value={jobType} onChange={(event) => setJobType(event.target.value)}><option value="competitor_check">Competitor check</option><option value="trend_scan">Trend scan</option><option value="content_research">Content research</option><option value="generic">Generic scrape</option></select></div>
            </>}
            <div className="field"><label htmlFor="scrape-cadence">Cadence</label><select id="scrape-cadence" value={cadence} onChange={(event) => setCadence(event.target.value as Cadence)}><option value="once">Run once</option><option value="daily">Daily recurring</option><option value="weekly">Weekly recurring</option><option value="monthly">Monthly recurring</option></select></div>
            <button className="button primary" type="submit" disabled={isBusy || (scrapeMode === "topic" ? topic.trim().length < 3 : !targetUrl.trim())}><Search size={16} aria-hidden="true" />{cadence === "once" ? (scrapeMode === "topic" ? "Run topic research once" : "Scrape URL once") : "Save scheduled scraper"}</button>
            <button className="button secondary" type="button" onClick={openSavedScrapedData} disabled={isLoadingResearch || isLoadingDocuments}>Saved drafts</button>
          </form>
        </aside>

        <div className="stack">
          {showSavedScrapedData ? (
            <article className="panel">
              <div className="panel-header"><h2>Saved scraped drafts</h2><div className="button-row"><button className="button ghost" type="button" onClick={() => { void loadResearch(); void loadDocuments(); }} disabled={isLoadingResearch || isLoadingDocuments}>Refresh</button><button className="button secondary" type="button" onClick={() => setShowSavedScrapedData(false)}>Back to preview</button></div></div>
              <div className="draft-list">
                {researchPacks.length === 0 && documents.length === 0 && researchJobs.length === 0 ? <div className="draft-item"><p>No saved drafts yet.</p></div> : null}
                {researchPacks.length ? <div className="notice">Topic research</div> : null}
                {researchPacks.map((pack) => <div className={selectedPackId === pack.id ? "draft-item selected" : "draft-item"} key={`pack-${pack.id}`}><button className="draft-select" type="button" onClick={() => selectResearchPack(pack.id)}><strong>{pack.topic}</strong><p>{pack.successful_source_count}/{pack.source_count} sources / {formatDate(pack.created_at)}{pack.content_draft_id ? " / content draft saved" : ""}</p></button></div>)}
                {documents.length ? <div className="notice">URL scrapes</div> : null}
                {documents.map((doc) => <div className={selectedId === doc.id ? "draft-item selected" : "draft-item"} key={`doc-${doc.id}`}><button className="draft-select" type="button" onClick={() => selectUrlDocument(doc.id)}><strong>{doc.title || doc.domain || doc.target_url}</strong><p>{doc.domain || doc.job_type} / {formatDate(doc.created_at)}</p></button></div>)}
                {researchJobs.length ? <div className="notice">Scheduled scraper drafts</div> : null}
                {researchJobs.map((job) => <div className="draft-item" key={`job-${job.id}`}><strong>{job.topic}</strong><p>{job.cadence} / next: {formatDate(job.next_run_at)}</p></div>)}
              </div>
            </article>
          ) : (
          <article className="panel">
            <div className="panel-header">
              <div>
                <h2>{selectedPreviewTitle}</h2>
                <p>{selectedPreviewKind}</p>
              </div>
              <div className="button-row">
                {selectedDocument ? <a className="button ghost" href={selectedDocument.target_url} target="_blank" rel="noreferrer"><ExternalLink size={16} aria-hidden="true" />Open source</a> : null}
                {(selectedPack || selectedDocument) ? <button className="button ghost" type="button" onClick={selectedPack ? closeResearchPreview : closeUrlPreview}>Close</button> : null}
                <span className={selectedPack || selectedDocument ? "status-badge success" : "status-badge neutral"}>{selectedPreviewKind}</span>
              </div>
            </div>
            <pre className="stream-output mono">{selectedPreviewBody.slice(0, 10000)}</pre>
            <div className="button-row with-top-gap">
              <button className="button primary" type="button" onClick={generateSelectedPost} disabled={(!selectedPack && !selectedDocument) || isBusy}>
                <Sparkles size={16} aria-hidden="true" />
                Generate post
              </button>
              <button className="button secondary" type="button" onClick={() => selectedPack ? void saveResearchDataDraft() : void saveUrlDataDraft()} disabled={(!selectedPack && !selectedDocument) || isBusy}>
                Save scraped data in draft
              </button>
              <button className="button danger" type="button" onClick={() => void deleteSelectedScrapedData()} disabled={(!selectedPack && !selectedDocument) || isBusy}>
                Delete
              </button>
            </div>
          </article>
          )}
        </div>
      </div>

      {notice ? <div className="notice with-top-gap">{notice}</div> : null}
    </section>
  );
}

