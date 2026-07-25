from dataclasses import dataclass
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx

from app.config import Settings
from app.errors import ScraperError


@dataclass
class DiscoveredSource:
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None
    source_provider: str = "google"


async def discover_sources(topic: str, settings: Settings, limit: int) -> list[DiscoveredSource]:
    """Discover candidate source pages for a topic.

    SerpAPI is the primary provider so topic research uses Google search results.
    If no SerpAPI key is configured, the previous RSS endpoint remains as a local
    development fallback instead of hard-failing the whole scraper.
    """
    if settings.serpapi_api_key:
        return await discover_sources_with_serpapi(topic, settings, limit)
    return await discover_sources_with_rss_fallback(topic, settings, limit)


async def discover_sources_with_serpapi(topic: str, settings: Settings, limit: int) -> list[DiscoveredSource]:
    params: dict[str, str | int] = {
        "engine": settings.serpapi_engine,
        "q": topic,
        "api_key": settings.serpapi_api_key,
        "num": min(max(limit, 1), 20),
        "gl": settings.serpapi_gl,
        "hl": settings.serpapi_hl,
        "google_domain": settings.serpapi_google_domain,
    }
    if settings.serpapi_tbm:
        params["tbm"] = settings.serpapi_tbm

    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True, trust_env=False) as client:
            response = await client.get(settings.serpapi_search_endpoint, params=params, headers={"User-Agent": settings.user_agent})
    except httpx.TimeoutException as exc:
        raise ScraperError("source_discovery_timeout", "SerpAPI did not respond before the scraper timeout.", 504) from exc
    except httpx.RequestError as exc:
        raise ScraperError("source_discovery_failed", f"Unable to reach SerpAPI for Google source discovery: {exc.__class__.__name__}", 502) from exc

    if response.status_code in (401, 403):
        raise ScraperError(
            "serpapi_auth_failed",
            "SerpAPI rejected the configured API key. Add a valid SCRAPER_SERPAPI_API_KEY and restart the scraper service.",
            response.status_code,
        )
    if response.status_code >= 400:
        raise ScraperError("source_discovery_failed", f"SerpAPI source discovery failed with HTTP {response.status_code}.", 502)

    try:
        payload = response.json()
    except ValueError as exc:
        raise ScraperError("source_discovery_invalid", "SerpAPI returned invalid JSON data.", 502) from exc

    if isinstance(payload, dict) and payload.get("error"):
        raise ScraperError("source_discovery_failed", f"SerpAPI rejected the search request: {payload.get('error')}", 502)

    sources: list[DiscoveredSource] = []
    seen: set[str] = set()

    def add(title: str | None, link: str | None, snippet: str | None = None, date: str | None = None) -> None:
        if len(sources) >= limit:
            return
        if not link or not urlparse(link).scheme.startswith("http") or link in seen:
            return
        if is_google_owned_result(link):
            return
        seen.add(link)
        sources.append(
            DiscoveredSource(
                title=(title or link).strip(),
                url=link.strip(),
                snippet=(snippet or "").strip(),
                published_at=(date or None),
                source_provider="serpapi_google",
            )
        )

    for key in ("news_results", "top_stories", "organic_results"):
        items = payload.get(key) if isinstance(payload, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            add(
                item.get("title"),
                item.get("link") or item.get("url"),
                item.get("snippet") or item.get("source") or item.get("description"),
                item.get("date") or item.get("published_at"),
            )

    answer_box = payload.get("answer_box") if isinstance(payload, dict) else None
    if isinstance(answer_box, dict):
        add(answer_box.get("title"), answer_box.get("link"), answer_box.get("snippet") or answer_box.get("answer"))

    if not sources:
        raise ScraperError("source_discovery_empty", "Google returned no crawlable sources for this topic.", 404)
    return sources[:limit]


def is_google_owned_result(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("google.com") or host.endswith("googleusercontent.com") or host.endswith("gstatic.com")


async def discover_sources_with_rss_fallback(topic: str, settings: Settings, limit: int) -> list[DiscoveredSource]:
    from urllib.parse import quote_plus

    query = quote_plus(topic)
    url = f"{settings.research_search_endpoint}?q={query}&format=rss"
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True, trust_env=False) as client:
            response = await client.get(url, headers={"User-Agent": settings.user_agent})
        response.raise_for_status()
    except Exception as exc:
        raise ScraperError("source_discovery_failed", f"Unable to discover sources for this topic: {exc}", 502) from exc

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        raise ScraperError("source_discovery_invalid", "Search provider returned invalid RSS data.", 502) from exc

    sources: list[DiscoveredSource] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        link = text_of(item, "link")
        if not link or not urlparse(link).scheme.startswith("http") or link in seen:
            continue
        seen.add(link)
        sources.append(
            DiscoveredSource(
                title=text_of(item, "title") or link,
                url=link,
                snippet=text_of(item, "description"),
                published_at=text_of(item, "pubDate") or None,
                source_provider="rss_fallback",
            )
        )
        if len(sources) >= limit:
            break
    if not sources:
        raise ScraperError("source_discovery_empty", "No sources were found for this topic.", 404)
    return sources


def text_of(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    return (child.text or "").strip() if child is not None else ""

