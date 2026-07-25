"use client";

import { useEffect, useState } from "react";
import { ExternalLink, FileText, Search, Sparkles } from "lucide-react";
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
  source_query?: string | null;
  content?: string | null;
  excerpt?: string | null;
  word_count?: number | null;
  document_id?: string | null;
  error_reason?: string | null;
  raw?: ScrapeDocument["raw"];
  source_provider?: string | null;
};

type ResearchSourceSection = {
  query: string;
  total_source_count: number;
  successful_source_count: number;
  sources: ResearchSource[];
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
  source_sections?: ResearchSourceSection[];
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
  const sections = pack.source_sections?.length ? pack.source_sections : groupResearchSources(pack.sources ?? []);
  const marketData = sections.map((section) => {
    const completed = section.sources.filter((source) => source.status === "completed");
    const completedText = completed.map((source, index) => {
      const body = source.content || source.excerpt || stringifyValue(source.raw?.markdown || source.raw?.extracted_content || source.snippet);
      return `${index + 1}. ${source.title || source.url}\nSource: ${source.url}\nWords scraped: ${source.word_count ?? "unknown"}\n\n${body}`;
    }).join("\n\n---\n\n");
    return `Research focus: ${section.query}\n${completedText || "No meaningful article/body text was extracted for this source group."}`;
  }).join("\n\n====================\n\n");
  return `Topic: ${pack.topic}\n\nKey points from scraped market data:\n${points}\n\nScraped market data:\n${marketData || "No meaningful article/body text was extracted. Try a more specific topic or fewer sources."}`;
}

function sourcePreviewText(source: ResearchSource) {
  return source.content || source.excerpt || stringifyValue(source.raw?.markdown || source.raw?.extracted_content || source.snippet) || "No readable body text was extracted from this source.";
}

const RESEARCH_VALUE_KEYWORDS = [
  "market",
  "growth",
  "decline",
  "revenue",
  "profit",
  "loss",
  "forecast",
  "trend",
  "risk",
  "investor",
  "customer",
  "company",
  "stock",
  "shares",
  "announced",
  "reported",
  "launched",
  "data",
  "demand",
  "price",
  "billion",
  "million",
  "%",
  "$"
];

function valuableSourceBrief(source: ResearchSource) {
  const rawText = [source.snippet, sourcePreviewText(source)].filter(Boolean).join("\n");
  const candidateLines = rawText
    .replace(/\r/g, "\n")
    .split(/\n|(?<=[.!?])\s+/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter((line) => line.length >= 35 && line.length <= 280)
    .filter((line) => !/(accept cookies|privacy policy|terms of use|all rights reserved|subscribe|sign up|advertisement|enable javascript|cookie policy|newsletter|log in|http|www\.)/i.test(line));

  const seen = new Set<string>();
  const scored = candidateLines.map((line, index) => {
    const lower = line.toLowerCase();
    let score = 0;
    score += RESEARCH_VALUE_KEYWORDS.reduce((total, keyword) => total + (lower.includes(keyword) ? 5 : 0), 0);
    score += /\d/.test(line) ? 10 : 0;
    score += /[%$]/.test(line) ? 8 : 0;
    score += /\b(announced|reported|grew|fell|launched|forecast|expects|plans|raised|cut)\b/i.test(line) ? 8 : 0;
    score += line.length >= 60 && line.length <= 220 ? 4 : 0;
    return { line, index, score };
  });

  const selected = scored
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .filter((item) => {
      const key = item.line.toLowerCase().slice(0, 130);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 5)
    .sort((a, b) => a.index - b.index)
    .map((item) => `- ${clipText(item.line, 220)}`);

  return selected.length ? selected.join("\n") : "- The selected source did not contain enough clean article text. Write a cautious, general LinkedIn post without inventing specific facts.";
}

function selectedSourceGenerationPrompt(source: ResearchSource) {
  const usefulBrief = valuableSourceBrief(source);
  const sourceTitle = source.title ? `Source context: ${source.title}
` : "";
  return `Write an impactful LinkedIn post from the extracted research points below. Use only these points. Do not mention scraping, prompts, URLs, or missing data. Do not add unsupported facts. Make it professional, clear, and engaging.

${sourceTitle}Key points:
${usefulBrief}`;
}

function groupResearchSources(sources: ResearchSource[]) {
  const groups = new Map<string, ResearchSource[]>();
  for (const source of sources) {
    const key = source.source_query?.trim() || "Research topic";
    const current = groups.get(key) ?? [];
    current.push(source);
    groups.set(key, current);
  }
  return Array.from(groups.entries()).map(([query, items]) => ({
    query,
    total_source_count: items.length,
    successful_source_count: items.filter((item) => item.status === "completed").length,
    sources: items
  }));
}

function sourceProviderLabel(source: ResearchSource) {
  if (source.source_provider === "serpapi_google") return "Google result";
  if (source.source_provider === "rss_fallback") return "Search fallback";
  return source.source_provider || "Discovered source";
}

function completedResearchSources(pack: ResearchPack | null) {
  return (pack?.sources ?? []).filter((source) => source.status === "completed");
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
  const [cadence, setCadence] = useState<Cadence>("once");
  const [topic, setTopic] = useState("");
  const [maxSources, setMaxSources] = useState(5);
  const [autoGeneratePost, setAutoGeneratePost] = useState(false);
  const [researchPacks, setResearchPacks] = useState<ResearchPackSummary[]>([]);
  const [researchJobs, setResearchJobs] = useState<ResearchJob[]>([]);
  const [selectedPackId, setSelectedPackId] = useState<string | null>(null);
  const [selectedPack, setSelectedPack] = useState<ResearchPack | null>(null);
  const [notice, setNotice] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [isLoadingResearch, setIsLoadingResearch] = useState(false);
  const [showSavedScrapedData, setShowSavedScrapedData] = useState(false);

  const authHeaders = () => ({ Authorization: `Bearer ${accessToken}` });

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
    void loadResearch();
  }, [activeAccount?.id, accessToken]);


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

  const selectResearchPack = (packId: string) => {
    setSelectedPackId(packId);
    setShowSavedScrapedData(false);
  };

  const openSavedScrapedData = () => {
    setShowSavedScrapedData(true);
    void loadResearch();
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

  const sendResearchToContentStudio = () => {
    if (!selectedPack) {
      setNotice("Select a research pack first.");
      return;
    }
    const prompt = `Write a professional ${selectedPack.output_type?.replaceAll("_", " ") || "LinkedIn post"} using the scraped research brief below. Do not invent facts. Make it useful, polished, and suitable for social media.\n\n${researchGenerationBrief(selectedPack)}`;
    window.sessionStorage.setItem(SCRAPER_PROMPT_HANDOFF_KEY, JSON.stringify({ prompt, autoGenerate: true }));
    router.push("/content-studio");
  };


  const sendSourceToContentStudio = (source: ResearchSource, sectionQuery?: string) => {
    const prompt = selectedSourceGenerationPrompt(source);
    window.sessionStorage.setItem(SCRAPER_PROMPT_HANDOFF_KEY, JSON.stringify({ prompt, autoGenerate: true }));
    router.push("/content-studio");
  };

  const selectedPreviewTitle = selectedPack?.topic || "Scraped data preview";
  const selectedPreviewBody = selectedPack ? researchPreview(selectedPack) : "Run or select a research pack to preview scraped data.";
  const selectedPreviewKind = selectedPack ? "Topic research" : "Idle";
  const selectedSourceSections = selectedPack?.source_sections?.length ? selectedPack.source_sections : groupResearchSources(selectedPack?.sources ?? []);

  const generateSelectedPost = () => {
    if (selectedPack) {
      sendResearchToContentStudio();
      return;
    }
    setNotice("Select scraped data first.");
  };

  const deleteSelectedScrapedData = async () => {
    if (!accessToken) return;
    const packId = selectedPack?.id;
    if (!packId) {
      setNotice("Select scraped data first.");
      return;
    }
    setIsBusy(true);
    setNotice("");
    try {
      const response = await fetch(`/api/scraper/research-packs/${packId}`, { method: "DELETE", headers: authHeaders() });
      if (!response.ok) throw new Error(await readError(response, `Delete failed (${response.status}).`));
      setResearchPacks((current) => current.filter((pack) => pack.id !== packId));
      closeResearchPreview();
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
            <FileText size={22} color="var(--color-primary)" aria-hidden="true" />
            <h2>Configure scraper</h2>
            <div className="field"><label htmlFor="research-topic">What data should we scrape?</label><textarea id="research-topic" value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Example: Latest stock market news for fintech founders" /></div>
            <div className="field"><label htmlFor="max-sources">Sources per run</label><input id="max-sources" type="number" min={1} max={10} value={maxSources} onChange={(event) => setMaxSources(Number(event.target.value))} /></div>
            {cadence !== "once" ? <label className="check-row"><input type="checkbox" checked={autoGeneratePost} onChange={(event) => setAutoGeneratePost(event.target.checked)} /><span>Auto-generate post after scheduled runs</span></label> : null}
            <div className="field"><label htmlFor="scrape-cadence">Cadence</label><select id="scrape-cadence" value={cadence} onChange={(event) => setCadence(event.target.value as Cadence)}><option value="once">Run once</option><option value="daily">Daily recurring</option><option value="weekly">Weekly recurring</option><option value="monthly">Monthly recurring</option></select></div>
            <button className="button primary" type="submit" disabled={isBusy || topic.trim().length < 3}><Search size={16} aria-hidden="true" />{cadence === "once" ? "Run research once" : "Save scheduled scraper"}</button>
            <button className="button secondary" type="button" onClick={openSavedScrapedData} disabled={isLoadingResearch}>Saved drafts</button>
          </form>
        </aside>

        <div className="stack">
          {showSavedScrapedData ? (
            <article className="panel">
              <div className="panel-header"><h2>Saved scraped drafts</h2><div className="button-row"><button className="button ghost" type="button" onClick={() => { void loadResearch(); }} disabled={isLoadingResearch}>Refresh</button><button className="button secondary" type="button" onClick={() => setShowSavedScrapedData(false)}>Back to preview</button></div></div>
              <div className="draft-list">
                {researchPacks.length === 0 && researchJobs.length === 0 ? <div className="draft-item"><p>No saved drafts yet.</p></div> : null}
                {researchPacks.length ? <div className="notice">Topic research</div> : null}
                {researchPacks.map((pack) => <div className={selectedPackId === pack.id ? "draft-item selected" : "draft-item"} key={`pack-${pack.id}`}><button className="draft-select" type="button" onClick={() => selectResearchPack(pack.id)}><strong>{pack.topic}</strong><p>{pack.successful_source_count}/{pack.source_count} sources / {formatDate(pack.created_at)}{pack.content_draft_id ? " / content draft saved" : ""}</p></button></div>)}
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
                {selectedPack ? <button className="button ghost" type="button" onClick={closeResearchPreview}>Close</button> : null}
                <span className={selectedPack ? "status-badge success" : "status-badge neutral"}>{selectedPreviewKind}</span>
              </div>
            </div>
            {selectedPack ? (
              <div className="research-source-list">
                {selectedSourceSections.length === 0 ? <div className="notice">No readable source content was extracted yet.</div> : null}
                {selectedSourceSections.map((section) => {
                  const completed = section.sources.filter((source) => source.status === "completed");
                  if (!completed.length) return null;
                  return (
                    <article className="research-source-card" key={section.query}>
                      <div className="panel-header compact">
                        <div>
                          <span className="status-badge neutral">Research focus</span>
                          <h3>{section.query}</h3>
                          <p>{completed.length} sources scraped</p>
                        </div>
                      </div>
                      <div className="research-source-list">
                        {completed.map((source, index) => (
                          <article className="research-source-card" key={source.document_id || source.url}>
                            <div className="panel-header compact">
                              <div>
                                <span className="status-badge success">Source {index + 1}</span>
                                <h4>{source.title || source.url}</h4>
                                <p>{sourceProviderLabel(source)} / {source.word_count?.toLocaleString() ?? "unknown"} words scraped</p>
                              </div>
                              <div className="button-row compact">
                                <button className="button primary compact" type="button" onClick={() => sendSourceToContentStudio(source, section.query)}>
                                  <Sparkles size={14} aria-hidden="true" />
                                  Generate post
                                </button>
                                <a className="button ghost compact" href={source.url} target="_blank" rel="noreferrer">
                                  <ExternalLink size={14} aria-hidden="true" />
                                  Open
                                </a>
                              </div>
                            </div>
                            {source.snippet ? <p className="muted-text">{source.snippet}</p> : null}
                            <pre className="stream-output mono">{sourcePreviewText(source).slice(0, 3500)}</pre>
                          </article>
                        ))}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <pre className="stream-output mono">{selectedPreviewBody.slice(0, 10000)}</pre>
            )}
            <div className="button-row with-top-gap">
              <button className="button primary" type="button" onClick={generateSelectedPost} disabled={!selectedPack || isBusy}>
                <Sparkles size={16} aria-hidden="true" />
                Generate post
              </button>
              <button className="button secondary" type="button" onClick={() => void saveResearchDataDraft()} disabled={!selectedPack || isBusy}>
                Save scraped data in draft
              </button>
              <button className="button danger" type="button" onClick={() => void deleteSelectedScrapedData()} disabled={!selectedPack || isBusy}>
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
