from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse
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


async def discover_sources(topic: str, settings: Settings, limit: int) -> list[DiscoveredSource]:
    query = quote_plus(topic)
    url = f"{settings.research_search_endpoint}?q={query}&format=rss"
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
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
