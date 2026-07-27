"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle, Download, ImagePlus, RadioTower, Save, Send, Sparkles, Square, Trash2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAuth } from "@/lib/auth-context";
import { streamAiGeneration } from "@/lib/sse-client";

type DraftItem = {
  id: string;
  title: string;
  body: string;
  prompt?: string | null;
  status?: string;
  image_url?: string | null;
  image_asset_ref?: string | null;
  metadata?: { has_image?: boolean } | null;
};

type DraftListResponse = {
  items: DraftItem[];
};

type CreditBalance = { balance: number };
type UsageSummary = { quota_tokens?: number | null; used_tokens: number; remaining_tokens?: number | null };
type CreditLedgerEntry = { amount: number; reason: string; source_event_id?: string | null; metadata?: Record<string, unknown> | null };
type PublishNowResponse = { status: string; linkedin_post_url?: string | null; job?: { linkedin_post_url?: string | null } };

const DEFAULT_PROMPT = "";
const SCRAPER_PROMPT_HANDOFF_KEY = "creditflow:scraper-prompt-handoff";
const SCHEDULE_CONTENT_HANDOFF_KEY = "creditflow:schedule-content-handoff";
const TEXT_GENERATION_CREDIT_COST = 100;

export function ContentStudio() {
  const router = useRouter();
  const { activeAccount, accessToken } = useAuth();
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [output, setOutput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [generateImageAlso, setGenerateImageAlso] = useState(false);
  const [isGeneratingImage, setIsGeneratingImage] = useState(false);
  const [imageUrl, setImageUrl] = useState("");
  const [imageDownloadUrl, setImageDownloadUrl] = useState("");
  const [hasImage, setHasImage] = useState(false);
  const [savedDrafts, setSavedDrafts] = useState<DraftItem[]>([]);
  const [isLoadingDrafts, setIsLoadingDrafts] = useState(false);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [isDraftBusy, setIsDraftBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [showSavedDrafts, setShowSavedDrafts] = useState(false);
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [usedTokens, setUsedTokens] = useState(0);
  const [remainingTokens, setRemainingTokens] = useState<number | null>(null);
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishChoiceDraft, setPublishChoiceDraft] = useState<DraftItem | null | undefined>(undefined);
  const stopStreamRef = useRef<(() => void) | null>(null);
  const outputRef = useRef("");
  const generateImageAlsoRef = useRef(false);

  useEffect(() => {
    return () => stopStreamRef.current?.();
  }, []);

  const readApiError = async (response: Response, fallback: string) => {
    const body = (await response.json().catch(() => null)) as { error?: string | { message?: string } } | null;
    const error = typeof body?.error === "string" ? body.error : body?.error?.message;
    return error || fallback;
  };

  const loadCreditUsage = async () => {
    if (!activeAccount || !accessToken) {
      setCreditBalance(null);
      setUsedTokens(0);
      setRemainingTokens(null);
      return;
    }
    try {
      const [balanceResponse, usageResponse, transactionsResponse] = await Promise.all([
        fetch("/api/credits/balance", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }),
        fetch(`/api/usage/usage/accounts/${encodeURIComponent(activeAccount.id)}/summary`, { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }),
        fetch("/api/credits/transactions?limit=200", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" })
      ]);
      if (balanceResponse.ok) {
        const balance = (await balanceResponse.json()) as CreditBalance;
        setCreditBalance(Number(balance.balance ?? 0));
      }
      let usageUsedTokens = 0;
      if (usageResponse.ok) {
        const usage = (await usageResponse.json()) as UsageSummary;
        usageUsedTokens = Number(usage.used_tokens ?? 0);
        setRemainingTokens(typeof usage.remaining_tokens === "number" ? usage.remaining_tokens : null);
      }
      if (transactionsResponse.ok) {
        const transactions = (await transactionsResponse.json()) as CreditLedgerEntry[];
        const aiCreditDelta = transactions
          .filter((entry) => entry.metadata?.kind === "ai_generation" || entry.source_event_id?.startsWith("ai.generation.reserve:"))
          .reduce((sum, entry) => sum + Number(entry.amount || 0), 0);
        setUsedTokens(Math.max(usageUsedTokens, Math.max(0, -aiCreditDelta)));
      } else {
        setUsedTokens(usageUsedTokens);
      }
    } catch {
      // Keep generation usable even if one dashboard metric is temporarily unavailable.
    }
  };

  useEffect(() => {
    generateImageAlsoRef.current = generateImageAlso;
  }, [generateImageAlso]);

  const loadDrafts = async () => {
    if (!activeAccount || !accessToken) {
      setSavedDrafts([]);
      return;
    }
    setIsLoadingDrafts(true);
    try {
      const [draftResponse, approvedResponse] = await Promise.all([
        fetch("/api/content/drafts?limit=50", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }),
        fetch("/api/content/drafts?status=approved&limit=50", { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" })
      ]);
      if (!draftResponse.ok) {
        const body = (await draftResponse.json().catch(() => null)) as { error?: string | { message?: string } } | null;
        const error = typeof body?.error === "string" ? body.error : body?.error?.message;
        throw new Error(error || `Drafts failed to load (${draftResponse.status}).`);
      }
      const drafts = (await draftResponse.json()) as DraftListResponse;
      const approved = approvedResponse.ok ? ((await approvedResponse.json()) as DraftListResponse) : { items: [] };
      const merged = [...(drafts.items ?? []), ...(approved.items ?? [])].filter((draft, index, items) => items.findIndex((item) => item.id === draft.id) === index);
      setSavedDrafts(merged);
      if (selectedDraftId && !merged.some((draft) => draft.id === selectedDraftId)) {
        clearSelectedDraft();
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Drafts failed to load.");
    } finally {
      setIsLoadingDrafts(false);
    }
  };

  useEffect(() => {
    void loadDrafts();
    void loadCreditUsage();
  }, [activeAccount?.id, accessToken]);

  const generateImageFromText = async (text: string) => {
    const sourceText = text.trim();
    if (!sourceText || !accessToken) {
      return;
    }
    setIsGeneratingImage(true);
    setNotice("");
    try {
      const response = await fetch("/api/ai/image", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({ source_text: sourceText })
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { error?: string | { message?: string } } | null;
        const error = typeof body?.error === "string" ? body.error : body?.error?.message;
        throw new Error(error || `Image generation failed (${response.status}).`);
      }
      const data = (await response.json()) as { id: string; image_url?: string; download_url?: string };
      setImageUrl(data.image_url ?? "");
      setImageDownloadUrl(data.download_url ? `/api/ai/image/${data.id}/download` : "");
      setHasImage(Boolean(data.image_url));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Image generation failed.");
    } finally {
      setIsGeneratingImage(false);
    }
  };

  const downloadGeneratedImage = async () => {
    if (!imageDownloadUrl || !accessToken) {
      return;
    }
    try {
      const response = await fetch(imageDownloadUrl, { headers: { Authorization: `Bearer ${accessToken}` } });
      if (!response.ok) {
        throw new Error(`Image download failed (${response.status}).`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "creditflow-generated-image.jpg";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Image download failed.");
    }
  };

  const startGeneration = async (promptOverride?: string) => {
    if (!activeAccount) {
      return;
    }

    if ((creditBalance ?? 0) < TEXT_GENERATION_CREDIT_COST) {
      setNotice(`Not enough credits to generate this post. At least ${TEXT_GENERATION_CREDIT_COST} credits are required.`);
      return;
    }

    const promptToUse = promptOverride ?? prompt;
    if (promptOverride) {
      setPrompt(promptOverride);
    }

    stopStreamRef.current?.();
    setOutput("");
    outputRef.current = "";
    setImageUrl("");
    setImageDownloadUrl("");
    setHasImage(false);
    setNotice("");
    setCreditBalance((current) => (typeof current === "number" ? Math.max(0, current - TEXT_GENERATION_CREDIT_COST) : current));
    setUsedTokens((current) => current + TEXT_GENERATION_CREDIT_COST);
    setIsStreaming(true);
    window.setTimeout(() => void loadCreditUsage(), 500);

    stopStreamRef.current = streamAiGeneration({
      prompt: promptToUse,
      accountId: activeAccount.id,
      accessToken,
      onToken: (token) => {
        outputRef.current += token;
        setOutput(outputRef.current);
      },
      onDone: () => {
        setIsStreaming(false);
        stopStreamRef.current = null;
        window.setTimeout(() => void loadCreditUsage(), 800);
        window.setTimeout(() => void loadCreditUsage(), 2500);
        if (generateImageAlsoRef.current) {
          void generateImageFromText(outputRef.current);
        }
      },
      onError: (message) => {
        setIsStreaming(false);
        window.setTimeout(() => void loadCreditUsage(), 500);
        window.setTimeout(() => void loadCreditUsage(), 1800);
        setNotice(message.includes("quota") || message.includes("credit") ? "Not enough tokens to generate this post. Please buy more credits." : message);
      }
    });
  };

  useEffect(() => {
    if (!activeAccount || !accessToken) {
      return;
    }
    const raw = window.sessionStorage.getItem(SCRAPER_PROMPT_HANDOFF_KEY);
    if (!raw) {
      return;
    }
    try {
      const payload = JSON.parse(raw) as { prompt?: string; autoGenerate?: boolean };
      if (payload.prompt) {
        window.sessionStorage.removeItem(SCRAPER_PROMPT_HANDOFF_KEY);
        setPrompt(payload.prompt);
        setNotice("Scraped research loaded from the scraper. Generating post now.");
        if (payload.autoGenerate) {
          window.setTimeout(() => void startGeneration(payload.prompt), 0);
        }
      }
    } catch {
      setNotice("Unable to load scraped research handoff.");
    }
  }, [activeAccount?.id, accessToken]);

  const stopGeneration = () => {
    stopStreamRef.current?.();
    stopStreamRef.current = null;
    setIsStreaming(false);
  };

  const closeDraftEditor = () => {
    setSelectedDraftId(null);
    setDraftTitle("");
    setPrompt(DEFAULT_PROMPT);
    setOutput("");
    outputRef.current = "";
    setImageUrl("");
    setImageDownloadUrl("");
    setHasImage(false);
    setPublishChoiceDraft(undefined);
    setNotice("Draft closed. You can generate new content now.");
  };

  const clearSelectedDraft = () => {
    setSelectedDraftId(null);
    setDraftTitle("");
  };

  const selectDraft = (draft: DraftItem) => {
    stopStreamRef.current?.();
    stopStreamRef.current = null;
    setIsStreaming(false);
    setSelectedDraftId(draft.id);
    setDraftTitle(draft.title);
    setPrompt(draft.prompt ?? prompt);
    setOutput(draft.body);
    outputRef.current = draft.body;
    setImageUrl(draft.image_url ?? "");
    setImageDownloadUrl("");
    setHasImage(draftHasImage(draft));
    setShowSavedDrafts(false);
    setNotice("Draft loaded for editing.");
  };

  const openSavedDrafts = () => {
    setShowSavedDrafts(true);
    void loadDrafts();
  };

  const readDraftError = readApiError;

  const saveDraft = async (): Promise<DraftItem | null> => {
    if (!activeAccount) {
      return null;
    }

    if (!accessToken) {
      setNotice("You must be signed in to save a draft.");
      return null;
    }

    setIsDraftBusy(true);
    try {
      const isUpdating = Boolean(selectedDraftId);
      const response = await fetch(isUpdating ? `/api/content/items/${selectedDraftId}` : "/api/content/drafts", {
        method: isUpdating ? "PATCH" : "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          account_id: activeAccount.id,
          title: draftTitle || undefined,
          prompt,
          body: output,
          image_url: imageUrl || undefined,
          has_image: hasImage
        })
      });
      if (!response.ok) {
        throw new Error(await readDraftError(response, `Draft save failed (${response.status}).`));
      }
      const saved = (await response.json()) as DraftItem;
      if (isUpdating) {
        setSelectedDraftId(saved.id);
        setDraftTitle(saved.title);
      }
      setSavedDrafts((current) => [saved, ...current.filter((draft) => draft.id !== saved.id)]);
      setNotice(isUpdating ? "Draft updated." : "Draft saved to the active account.");
      return saved;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Draft save failed.");
      return null;
    } finally {
      setIsDraftBusy(false);
    }
  };

  const deleteDraft = async (draftId = selectedDraftId) => {
    if (!draftId || !accessToken) {
      return;
    }
    setIsDraftBusy(true);
    try {
      const response = await fetch(`/api/content/items/${draftId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!response.ok) {
        throw new Error(await readDraftError(response, `Draft delete failed (${response.status}).`));
      }
      setSavedDrafts((current) => current.filter((draft) => draft.id !== draftId));
      if (selectedDraftId === draftId) {
        clearSelectedDraft();
        setOutput("");
        outputRef.current = "";
        setImageUrl("");
        setHasImage(false);
      }
      setNotice("Draft deleted.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Draft delete failed.");
    } finally {
      setIsDraftBusy(false);
    }
  };


  const approveContentForPublish = async (contentId: string) => {
    const response = await fetch(`/api/content/items/${contentId}/approve`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` }
    });
    if (!response.ok && response.status !== 409) {
      throw new Error(await readApiError(response, `Content approval failed (${response.status}).`));
    }
  };

  const markContentPublished = async (contentId: string) => {
    const response = await fetch(`/api/content/items/${contentId}/publish`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` }
    });
    if (!response.ok && response.status !== 409) {
      throw new Error(await readApiError(response, `Content publish status update failed (${response.status}).`));
    }
  };

  const publishNow = async (draft?: DraftItem) => {
    if (!accessToken) {
      setNotice("You must be signed in to publish.");
      return;
    }
    setIsPublishing(true);
    setPublishChoiceDraft(undefined);
    setNotice("");
    try {
      let contentId: string | null | undefined = draft?.id ?? selectedDraftId;
      if (!contentId) {
        const saved = await saveDraft();
        contentId = saved?.id;
      }
      if (!contentId) {
        throw new Error("Save the post before publishing.");
      }
      await approveContentForPublish(contentId);
      const response = await fetch("/api/linkedin/publish-now", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ content_id: contentId })
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, `LinkedIn publish failed (${response.status}).`));
      }
      const result = (await response.json()) as PublishNowResponse;
      await markContentPublished(contentId);
      setSavedDrafts((current) => current.filter((item) => item.id !== contentId));
      if (selectedDraftId === contentId) {
        clearSelectedDraft();
      }
      const postUrl = result.linkedin_post_url || result.job?.linkedin_post_url;
      setNotice(postUrl ? `Published to LinkedIn: ${postUrl}` : "Published to LinkedIn.");
      void loadDrafts();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "LinkedIn publish failed.");
    } finally {
      setIsPublishing(false);
    }
  };


  const openPublishChoices = (draft?: DraftItem | null) => {
    setPublishChoiceDraft(draft ?? null);
    setNotice("");
  };

  const schedulePublish = async (draft?: DraftItem | null) => {
    if (!accessToken) {
      setNotice("You must be signed in to schedule publishing.");
      return;
    }
    setIsDraftBusy(true);
    setPublishChoiceDraft(undefined);
    try {
      let contentId = draft?.id ?? selectedDraftId;
      let title = draft?.title ?? draftTitle;
      if (!contentId) {
        const saved = await saveDraft();
        contentId = saved?.id ?? null;
        title = saved?.title ?? title;
      } else if (!draft) {
        const saved = await saveDraft();
        contentId = saved?.id ?? contentId;
        title = saved?.title ?? title;
      }
      if (!contentId) {
        throw new Error("Save the post before scheduling.");
      }
      window.sessionStorage.setItem(
        SCHEDULE_CONTENT_HANDOFF_KEY,
        JSON.stringify({
          contentId,
          title: title || "Untitled post",
          body: draft?.body ?? outputRef.current,
          status: draft?.status ?? savedDrafts.find((item) => item.id === contentId)?.status ?? "draft",
          image_url: draft?.image_url ?? (imageUrl || null),
          image_asset_ref: draft?.image_asset_ref ?? null,
          metadata: draft?.metadata ?? { has_image: hasImage }
        })
      );
      router.push("/calendar");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Schedule handoff failed.");
    } finally {
      setIsDraftBusy(false);
    }
  };

  const approveDraft = async (draftId = selectedDraftId) => {
    if (!draftId || !accessToken) {
      return;
    }
    setIsDraftBusy(true);
    try {
      const response = await fetch(`/api/content/items/${draftId}/approve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!response.ok) {
        throw new Error(await readDraftError(response, `Draft approval failed (${response.status}).`));
      }
      const approved = (await response.json()) as DraftItem;
      setSavedDrafts((current) => [approved, ...current.filter((draft) => draft.id !== approved.id)]);
      if (selectedDraftId === approved.id) {
        setSelectedDraftId(approved.id);
        setDraftTitle(approved.title);
      }
      setNotice("Draft approved.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Draft approval failed.");
    } finally {
      setIsDraftBusy(false);
    }
  };

  const draftHasImage = (draft: DraftItem) => Boolean(draft.image_url || draft.image_asset_ref || draft.metadata?.has_image);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Content studio</h1>
          <p className="page-subtitle">Generate text into the current account scope and save approved output as drafts.</p>
        </div>
        <div className="button-row compact">
          <span className="status-badge neutral">Credits {(creditBalance ?? 0).toLocaleString()}</span>
          <span className="status-badge neutral">Used credits {usedTokens.toLocaleString()}</span>
          <span className={isStreaming ? "status-badge live" : "status-badge neutral"}>
            {isStreaming ? "Streaming" : "Idle"}
          </span>
        </div>
      </div>

      <div className="studio-layout">
        <aside className="stack">
          <form
            className="panel form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              void startGeneration();
            }}
          >
            <RadioTower size={22} color="var(--color-primary)" aria-hidden="true" />
            <h2>Prompt</h2>
            <div className="field">
              <label htmlFor="prompt">Instruction</label>
              <textarea id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
            </div>
            <div className="button-row">
              <button className="button primary" type="submit" disabled={isStreaming || (creditBalance ?? 0) <= 0 || remainingTokens === 0}>
                <Sparkles size={16} aria-hidden="true" />
                Generate
              </button>
              <button className="icon-button ghost" type="button" onClick={stopGeneration} disabled={!isStreaming} aria-label="Stop generation">
                <Square size={16} aria-hidden="true" />
              </button>
              <button className="button secondary" type="button" onClick={openSavedDrafts} disabled={isLoadingDrafts}>
                Saved drafts
              </button>
            </div>
            <label className="check-row">
              <input type="checkbox" checked={generateImageAlso} onChange={(event) => setGenerateImageAlso(event.target.checked)} />
              <span>Generate image also</span>
            </label>
          </form>
        </aside>

        <div className="stack">
          {showSavedDrafts ? (
            <article className="panel">
              <div className="panel-header">
                <h2>Saved drafts</h2>
                <div className="button-row">
                  <button className="button ghost" type="button" onClick={() => void loadDrafts()} disabled={isLoadingDrafts}>Refresh</button>
                  <button className="button secondary" type="button" onClick={() => setShowSavedDrafts(false)}>Back to studio</button>
                </div>
              </div>
              <div className="draft-list">
                {isLoadingDrafts ? <div className="draft-item"><p>Loading drafts...</p></div> : null}
                {!isLoadingDrafts && savedDrafts.length === 0 ? <div className="draft-item"><p>No saved drafts yet.</p></div> : null}
                {savedDrafts.map((draft) => (
                  <div className={selectedDraftId === draft.id ? "draft-item selected" : "draft-item"} key={draft.id}>
                    <button className="draft-select" type="button" onClick={() => selectDraft(draft)}>
                      <strong>{draft.title}</strong>
                      <p>{draftHasImage(draft) ? "Text and image post" : "Text-only post"}{draft.status === "approved" ? " / Approved" : ""}</p>
                    </button>
                    <div className="button-row compact">
                      <button className="button ghost" type="button" onClick={() => selectDraft(draft)}>Edit</button>
                      <button className="button secondary" type="button" onClick={() => openPublishChoices(draft)} disabled={isDraftBusy || isPublishing}>
                        Publish
                      </button>
                      <button className="button secondary" type="button" onClick={() => void approveDraft(draft.id)} disabled={isDraftBusy || draft.status === "approved"}>
                        {draft.status === "approved" ? "Approved" : "Approve"}
                      </button>
                      <button className="icon-button danger" type="button" onClick={() => void deleteDraft(draft.id)} disabled={isDraftBusy} aria-label="Delete draft">
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              {notice ? <div className="notice with-top-gap">{notice}</div> : null}
            </article>
          ) : (
          <article className="panel">
            <div className="panel-header">
              <h2>{selectedDraftId ? "Edit draft" : "Live output"}</h2>
              <div className="button-row">
                {selectedDraftId ? (
                  <button className="button ghost" type="button" onClick={closeDraftEditor}>
                    <X size={16} aria-hidden="true" />
                    Close draft
                  </button>
                ) : null}
                {!selectedDraftId ? (
                  <>
                    <button className="button secondary" type="button" onClick={() => setHasImage(true)}>
                      <ImagePlus size={16} aria-hidden="true" />
                      Attach image
                    </button>
                    <button className="button secondary" type="button" onClick={() => void generateImageFromText(output)} disabled={!output || isGeneratingImage}>
                      <ImagePlus size={16} aria-hidden="true" />
                      {isGeneratingImage ? "Generating image" : "Generate image"}
                    </button>
                  </>
                ) : null}
                {imageDownloadUrl && !selectedDraftId ? (
                  <button className="button secondary" type="button" onClick={() => void downloadGeneratedImage()}>
                      <Download size={16} aria-hidden="true" />
                      Download image
                  </button>
                ) : null}
                <button className="button primary" type="button" onClick={() => void saveDraft()} disabled={!output || isDraftBusy}>
                  <Save size={16} aria-hidden="true" />
                  {selectedDraftId ? "Update draft" : "Save draft"}
                </button>
                {!selectedDraftId ? (
                  <button className="button secondary" type="button" onClick={() => openPublishChoices(null)} disabled={!output || isDraftBusy || isPublishing}>
                    <Send size={16} aria-hidden="true" />
                    Publish
                  </button>
                ) : null}
                {selectedDraftId ? (
                  <>
                    <button className="button secondary" type="button" onClick={() => openPublishChoices(null)} disabled={isDraftBusy || isPublishing}>
                      <Send size={16} aria-hidden="true" />
                      Publish
                    </button>
                    <button className="button secondary" type="button" onClick={() => void approveDraft()} disabled={isDraftBusy || savedDrafts.find((draft) => draft.id === selectedDraftId)?.status === "approved"}>
                      <CheckCircle size={16} aria-hidden="true" />
                      {savedDrafts.find((draft) => draft.id === selectedDraftId)?.status === "approved" ? "Approved" : "Approve"}
                    </button>
                    <button className="button danger" type="button" onClick={() => void deleteDraft()} disabled={isDraftBusy}>
                      <Trash2 size={16} aria-hidden="true" />
                      Delete
                    </button>
                  </>
                ) : null}
              </div>
            </div>
            {selectedDraftId ? (
              <div className="field">
                <label htmlFor="draft-title">Draft title</label>
                <input id="draft-title" value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} />
              </div>
            ) : null}
            {selectedDraftId ? (
              <div className="field">
                <label htmlFor="draft-body">Draft body</label>
                <textarea
                  id="draft-body"
                  value={output}
                  onChange={(event) => {
                    outputRef.current = event.target.value;
                    setOutput(event.target.value);
                  }}
                />
              </div>
            ) : null}
            {!selectedDraftId ? (
              <div className={`stream-output ${isStreaming ? "live" : ""}`} aria-live="polite">
                {output ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{output}</ReactMarkdown>
                ) : (
                  <span className="stream-placeholder">Generated tokens will appear here.</span>
                )}
                {isStreaming ? <span className="stream-cursor" aria-hidden="true" /> : null}
              </div>
            ) : null}
            {isGeneratingImage ? <div className="generated-image-preview">Generating image from the final response...</div> : null}
            {imageUrl ? <img className="generated-image" src={imageUrl} alt="Generated post visual" /> : null}
            {hasImage && !imageUrl && !isGeneratingImage ? <div className="generated-image-preview">Image attached: this will publish as text and image.</div> : null}

            {publishChoiceDraft !== undefined ? (
              <div className="notice with-top-gap">
                <strong>Choose publishing option</strong>
                <p>{publishChoiceDraft?.title ?? (draftTitle || "Current post")}</p>
                <div className="button-row compact">
                  <button className="button primary compact" type="button" onClick={() => void publishNow(publishChoiceDraft ?? undefined)} disabled={isPublishing}>Publish now</button>
                  <button className="button secondary compact" type="button" onClick={() => void schedulePublish(publishChoiceDraft ?? null)} disabled={isDraftBusy}>Schedule publish</button>
                  <button className="button ghost compact" type="button" onClick={() => setPublishChoiceDraft(undefined)}>Cancel</button>
                </div>
              </div>
            ) : null}
            {notice ? <div className="notice">{notice}</div> : null}
          </article>
          )}
        </div>
      </div>

      {publishChoiceDraft !== undefined ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setPublishChoiceDraft(undefined)}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="publish-choice-title" onClick={(event) => event.stopPropagation()}>
            <h2 id="publish-choice-title">Publish this post</h2>
            <p>{publishChoiceDraft?.title ?? (draftTitle || "Current generated post")}</p>
            <div className="button-row">
              <button className="button primary" type="button" onClick={() => void publishNow(publishChoiceDraft ?? undefined)} disabled={isPublishing}>
                Publish now
              </button>
              <button className="button secondary" type="button" onClick={() => void schedulePublish(publishChoiceDraft ?? null)} disabled={isDraftBusy}>
                Schedule publish
              </button>
              <button className="button ghost" type="button" onClick={() => setPublishChoiceDraft(undefined)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

