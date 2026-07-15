"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle, Download, ImagePlus, RadioTower, Save, Sparkles, Square, Trash2, X } from "lucide-react";
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

const DEFAULT_PROMPT = "Write a LinkedIn post about account-scoped AI credit governance.";
const SCRAPER_PROMPT_HANDOFF_KEY = "creditflow:scraper-prompt-handoff";

export function ContentStudio() {
  const { activeAccount, accessToken, refreshAccessToken } = useAuth();
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
  const stopStreamRef = useRef<(() => void) | null>(null);
  const outputRef = useRef("");
  const generateImageAlsoRef = useRef(false);

  useEffect(() => {
    return () => stopStreamRef.current?.();
  }, []);

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
      const response = await fetch("/api/content/drafts?limit=20", {
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: "no-store"
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { error?: string | { message?: string } } | null;
        const error = typeof body?.error === "string" ? body.error : body?.error?.message;
        throw new Error(error || `Drafts failed to load (${response.status}).`);
      }
      const data = (await response.json()) as DraftListResponse;
      setSavedDrafts(data.items ?? []);
      if (selectedDraftId && !data.items?.some((draft) => draft.id === selectedDraftId)) {
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
    setIsStreaming(true);

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
        if (generateImageAlsoRef.current) {
          void generateImageFromText(outputRef.current);
        }
      },
      onError: (message) => {
        setIsStreaming(false);
        setNotice(message);
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
    window.sessionStorage.removeItem(SCRAPER_PROMPT_HANDOFF_KEY);
    try {
      const payload = JSON.parse(raw) as { prompt?: string; autoGenerate?: boolean };
      if (payload.prompt) {
        setPrompt(payload.prompt);
        setNotice("Scraped research loaded from the scraper. Generating post now.");
        if (payload.autoGenerate) {
          void startGeneration(payload.prompt);
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

  const readDraftError = async (response: Response, fallback: string) => {
    const body = (await response.json().catch(() => null)) as { error?: string | { message?: string } } | null;
    const error = typeof body?.error === "string" ? body.error : body?.error?.message;
    return error || fallback;
  };

  const saveDraft = async () => {
    if (!activeAccount) {
      return;
    }

    if (!accessToken) {
      setNotice("You must be signed in to save a draft.");
      return;
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
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Draft save failed.");
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
      setSavedDrafts((current) => current.filter((draft) => draft.id !== approved.id));
      if (selectedDraftId === approved.id) {
        clearSelectedDraft();
      }
      setNotice("Draft approved and removed from active drafts.");
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
        <span className={isStreaming ? "status-badge live" : "status-badge neutral"}>
          {isStreaming ? "Streaming" : "Idle"}
        </span>
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
              <button className="button primary" type="submit" disabled={isStreaming}>
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
                      <p>{draftHasImage(draft) ? "Text and image post" : "Text-only post"}</p>
                    </button>
                    <div className="button-row compact">
                      <button className="button ghost" type="button" onClick={() => selectDraft(draft)}>Edit</button>
                      <button className="button secondary" type="button" onClick={() => void approveDraft(draft.id)} disabled={isDraftBusy}>
                        Approve
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
                {selectedDraftId ? (
                  <>
                    <button className="button secondary" type="button" onClick={() => void approveDraft()} disabled={isDraftBusy}>
                      <CheckCircle size={16} aria-hidden="true" />
                      Approve
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
            {notice ? <div className="notice">{notice}</div> : null}
          </article>
          )}
        </div>
      </div>
    </section>
  );
}
