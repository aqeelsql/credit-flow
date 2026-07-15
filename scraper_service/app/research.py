import uuid
from datetime import datetime, timezone

from app.crawler import ScrapeRunner
from app.errors import ScraperError
from app.repository import ScraperRepository, as_jsonable, as_preview_text
from app.schemas import ScrapeRequested, TopicResearchRequest
from app.source_discovery import discover_sources


class ResearchRunner:
    def __init__(self, settings, repo: ScraperRepository):
        self.settings = settings
        self.repo = repo

    async def run(self, request: TopicResearchRequest, account_id: str | None, user_id: str | None, research_job_id: str | None = None) -> dict:
        sources = await discover_sources(request.topic, self.settings, min(max(request.max_sources * 3, request.max_sources), 15))
        source_results: list[dict] = []
        document_ids: list[str] = []
        for source in sources:
            if len([item for item in source_results if item.get("status") == "completed"]) >= request.max_sources:
                break
            event_id = f"research:{research_job_id or 'direct'}:{uuid.uuid4()}"
            payload = ScrapeRequested.model_validate(
                {
                    "event_id": event_id,
                    "account_id": account_id,
                    "requested_by_user_id": user_id,
                    "target_url": source.url,
                    "job_type": request.job_type,
                    "metadata": {**request.metadata, "topic": request.topic, "source_title": source.title, "research_job_id": research_job_id},
                }
            )
            try:
                result = await ScrapeRunner(self.settings, self.repo).run(payload)
                await self.repo.complete_event(event_id, result["document_id"])
                raw = result["document"].get("raw") or {}
                content = extract_research_text(raw)
                if not is_meaningful_research_text(content):
                    source_results.append({"status": "skipped", "title": source.title, "url": source.url, "snippet": source.snippet, "error_reason": "No meaningful article/body text was extracted from this source."})
                    continue
                document_ids.append(result["document_id"])
                source_results.append(
                    {
                        "status": "completed",
                        "document_id": result["document_id"],
                        "title": raw.get("title") or source.title,
                        "url": source.url,
                        "snippet": source.snippet,
                        "content": content,
                        "excerpt": content[:2200],
                        "word_count": len(content.split()),
                    }
                )
            except Exception as exc:
                source_results.append({"status": "failed", "title": source.title, "url": source.url, "snippet": source.snippet, "error_reason": getattr(exc, "message", str(exc))})

        key_points = build_key_points(source_results)
        if not key_points:
            blocked = [item for item in source_results if item.get("status") != "completed"]
            sample_reasons = "; ".join([str(item.get("error_reason") or item.get("status")) for item in blocked[:3]])
            raise ScraperError(
                "research_no_extractable_data",
                f"No meaningful market data could be extracted for this topic. Try a more specific topic or another market/source angle. Details: {sample_reasons or 'sources returned no body text'}",
                422,
            )
        pack = {
            "account_id": account_id,
            "created_by_user_id": user_id,
            "research_job_id": research_job_id,
            "topic": request.topic,
            "job_type": request.job_type,
            "output_type": request.output_type,
            "status": "completed" if any(item["status"] == "completed" for item in source_results) else "failed",
            "sources": source_results,
            "document_ids": document_ids,
            "key_points": key_points,
            "metadata": request.metadata,
            "created_at": datetime.now(timezone.utc),
        }
        pack_id = await self.repo.store_research_pack(pack)
        pack["id"] = pack_id
        return as_jsonable(pack)


def build_key_points(sources: list[dict]) -> list[str]:
    points: list[str] = []
    for source in sources:
        if source.get("status") != "completed":
            continue
        text = source.get("content") or extract_research_text(source.get("raw") or {}) or source.get("snippet")
        clean = " ".join(text.split())
        if clean:
            points.append(f"{source.get('title')}: {clean[:420]}")
        if len(points) >= 6:
            break
    return points


def extract_research_text(raw: dict) -> str:
    text = as_preview_text(raw.get("markdown") or raw.get("extracted_content") or "")
    if not text:
        text = as_preview_text(raw.get("cleaned_html") or "")
    return clean_research_text(text)


def clean_research_text(text: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for line in text.replace("\r", "\n").split("\n"):
        clean = " ".join(line.split()).strip()
        if len(clean) < 35:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        if any(skip in lowered for skip in ("accept cookies", "sign up", "subscribe", "advertisement", "all rights reserved", "privacy policy", "terms of use")):
            continue
        seen.add(lowered)
        lines.append(clean)
    cleaned = "\n\n".join(lines)
    return cleaned[:12000]


def is_meaningful_research_text(text: str) -> bool:
    words = text.split()
    if len(words) < 80:
        return False
    linkish_words = len([word for word in words if word.startswith(("http://", "https://", "www."))])
    return linkish_words / max(len(words), 1) < 0.08
