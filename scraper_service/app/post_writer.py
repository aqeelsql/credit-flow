import httpx

from app.config import Settings
from app.errors import ScraperError


def build_social_prompt(pack: dict, output_type: str) -> str:
    sources = pack.get("sources") or []
    source_lines = []
    for index, source in enumerate(sources[:8], start=1):
        raw = source.get("raw") or {}
        text = raw.get("markdown") or raw.get("extracted_content") or source.get("snippet") or ""
        source_lines.append(f"Source {index}: {source.get('title') or source.get('url')}\nURL: {source.get('url')}\nExtract: {str(text)[:1400]}")
    return f"""Write a polished {output_type.replace('_', ' ')} for a professional social media audience.

Research topic: {pack.get('topic')}

Use only the research below. Do not invent facts. Keep it clear, useful, and credible. Include 3-5 concise paragraphs and a short call to action. Do not include raw citations, but make the post sound grounded in current research.

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
