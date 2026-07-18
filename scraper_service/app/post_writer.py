import httpx

from app.config import Settings
from app.errors import ScraperError


def clean_for_prompt(value: object, max_chars: int) -> str:
    text = str(value or "")
    lines: list[str] = []
    seen: set[str] = set()
    for line in text.replace("\r", "\n").split("\n"):
        clean = " ".join(line.split()).strip()
        if len(clean) < 30:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        if any(skip in lowered for skip in ("accept cookies", "privacy policy", "terms of use", "all rights reserved", "subscribe", "sign up", "advertisement", "enable javascript")):
            continue
        seen.add(lowered)
        lines.append(clean)
    cleaned = "\n".join(lines) or " ".join(text.split())
    return cleaned[:max_chars]


def build_social_prompt(pack: dict, output_type: str) -> str:
    sources = pack.get("sources") or []
    source_lines = []
    completed_sources = [source for source in sources if source.get("status") == "completed"] or sources
    for index, source in enumerate(completed_sources[:6], start=1):
        raw = source.get("raw") or {}
        text = source.get("content") or source.get("excerpt") or raw.get("markdown") or raw.get("extracted_content") or source.get("snippet") or ""
        source_lines.append(f"Source {index}: {source.get('title') or source.get('url')}\nURL: {source.get('url')}\nExtracted facts/data:\n{clean_for_prompt(text, 1800)}")
    key_points = "\n".join(f"- {clean_for_prompt(point, 420)}" for point in (pack.get("key_points") or [])[:8])
    research_brief = clean_for_prompt(pack.get("research_brief") or "", 1800)
    if not source_lines and not key_points and not research_brief:
        raise ScraperError("research_pack_empty", "This research pack has no usable extracted text for post generation.", 422)
    return f"""Write a polished {output_type.replace('_', ' ')} for a professional social media audience.

Research topic: {pack.get('topic')}

Use only the research below. Do not invent facts. If the research is thin, say what is observable instead of pretending certainty. Keep it clear, useful, and credible. Include 3-5 concise paragraphs and a short call to action. Do not paste raw URLs in the post.

Research brief:
{research_brief or 'No separate brief available.'}

Key facts:
{key_points or 'Use the source extracts below.'}

Research:
{chr(10).join(source_lines)}
""".strip()


async def generate_social_post(settings: Settings, pack: dict, output_type: str) -> str:
    if not settings.openrouter_api_key or not settings.openrouter_model:
        raise ScraperError("llm_not_configured", "OpenRouter API key/model are required to generate a post.", 503)
    prompt = build_social_prompt(pack, output_type)
    models = [settings.openrouter_model]
    if settings.openrouter_fallback_model and settings.openrouter_fallback_model not in models:
        models.append(settings.openrouter_fallback_model)
    last_error: Exception | None = None
    for model in models:
        try:
            async with httpx.AsyncClient(timeout=settings.openrouter_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "max_tokens": 700, "temperature": 0.55},
                )
            if response.is_error:
                last_error = ScraperError("llm_rejected", "OpenRouter rejected the research post request.", 502, {"status": response.status_code, "body": response.text[:500]})
                continue
            data = response.json()
            choices = data.get("choices") or []
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            content = str(content).strip()
            if content:
                return content
        except Exception as exc:
            last_error = exc
    if isinstance(last_error, ScraperError):
        raise last_error
    raise ScraperError("llm_failed", f"Unable to generate a social post: {last_error}", 502)


async def save_content_draft(settings: Settings, principal, pack: dict, post_text: str, prompt: str) -> dict:
    title = f"Research post: {pack.get('topic', 'Untitled')}"[:180]
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{settings.content_service_url.rstrip('/')}/drafts",
                headers={
                    "Content-Type": "application/json",
                    "x-user-id": principal.user_id or "system",
                    "x-account-id": principal.account_id or "default",
                    "x-role": principal.role or "Owner",
                },
                json={"title": title, "body": post_text, "prompt": prompt, "metadata": {"source": "scraper_research_pack", "research_pack_id": pack.get("id"), "topic": pack.get("topic")}},
            )
        if response.is_error:
            raise ScraperError("content_draft_failed", "Content Service rejected the generated draft.", 502, {"status": response.status_code, "body": response.text[:500]})
        return response.json()
    except ScraperError:
        raise
    except Exception as exc:
        raise ScraperError("content_draft_failed", f"Unable to save generated post as content draft: {exc}", 502) from exc
