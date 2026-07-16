import asyncio
import re
import os
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import Settings
from app.errors import ScraperError
from app.repository import ScraperRepository, as_jsonable


NOISE_TEXT_PATTERNS = (
    "accept cookies",
    "privacy policy",
    "terms of use",
    "all rights reserved",
    "subscribe",
    "sign up",
    "advertisement",
    "enable javascript",
    "cookie policy",
    "newsletter",
)


def domain_for(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower()


async def robots_allowed(url: str, settings: Settings) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(robots_url, headers={"User-Agent": settings.user_agent})
        if response.status_code >= 400:
            return True
        parser.parse(response.text.splitlines())
        return parser.can_fetch(settings.user_agent, url)
    except Exception:
        return True


async def crawl_url(url: str, settings: Settings) -> dict:
    os.makedirs(settings.crawl4ai_base_directory, exist_ok=True)
    os.environ.setdefault("CRAWL4_AI_BASE_DIRECTORY", settings.crawl4ai_base_directory)
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except Exception as exc:
        return await crawl_url_with_http_fallback(url, settings, f"Crawl4AI import failed: {exc}")

    try:
        browser_config = BrowserConfig(headless=True, user_agent=settings.user_agent)
        run_config = CrawlerRunConfig(verbose=False)
        async with AsyncWebCrawler(config=browser_config, base_directory=settings.crawl4ai_base_directory) as crawler:
            result = await crawler.arun(url=url, config=run_config)
    except Exception as exc:
        return await crawl_url_with_http_fallback(url, settings, str(exc))

    return as_jsonable(
        {
            "success": bool(getattr(result, "success", True)),
            "title": getattr(result, "title", None),
            "markdown": getattr(result, "markdown", None),
            "cleaned_html": getattr(result, "cleaned_html", None),
            "extracted_content": getattr(result, "extracted_content", None),
            "links": getattr(result, "links", None),
            "media": getattr(result, "media", None),
            "metadata": getattr(result, "metadata", None),
            "error_message": getattr(result, "error_message", None),
        }
    )


async def crawl_url_with_http_fallback(url: str, settings: Settings, fallback_reason: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": settings.user_agent})
        response.raise_for_status()
    except Exception as exc:
        raise ScraperError(
            "crawl_runtime_error",
            f"Crawl4AI browser failed ({fallback_reason}) and HTTP fallback also failed: {exc}",
            502,
        ) from exc

    title = None
    links = []
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "form", "iframe"]):
            tag.decompose()
        for selector in ("nav", "footer", "header", "aside", "[role='navigation']", "[aria-label='breadcrumb']"):
            for tag in soup.select(selector):
                tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        text = extract_best_text_from_soup(soup)
        links = [
            {"text": anchor.get_text(" ", strip=True), "href": anchor.get("href")}
            for anchor in soup.find_all("a", href=True)[:200]
        ]
        cleaned_html = str(soup.body or soup)[:200000]
    except Exception:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL)
        title = unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else None
        without_noise = re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<noscript[^>]*>.*?</noscript>", " ", response.text, flags=re.IGNORECASE | re.DOTALL)
        text = unescape(re.sub(r"<[^>]+>", "\n", without_noise))
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        cleaned_html = without_noise[:200000]
    metadata = {
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type"),
        "fallback_reason": fallback_reason,
    }
    return as_jsonable(
        {
            "success": True,
            "title": title,
            "markdown": text,
            "cleaned_html": cleaned_html,
            "extracted_content": text,
            "links": links,
            "media": [],
            "metadata": metadata,
            "error_message": None,
            "crawler_fallback": "httpx+html-parser",
        }
    )


def extract_best_text_from_soup(soup) -> str:
    candidates = []
    for selector in ("article", "main", "[role='main']", ".article", ".post", ".entry-content", ".content", "body"):
        for node in soup.select(selector):
            text = clean_extracted_lines(node.get_text("\n", strip=True))
            score = score_extracted_text(text)
            if score > 0:
                candidates.append((score, text))
    if not candidates:
        return clean_extracted_lines(soup.get_text("\n", strip=True))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def clean_extracted_lines(text: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for line in text.replace("\r", "\n").split("\n"):
        clean = " ".join(line.split()).strip()
        if len(clean) < 28:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        if any(pattern in lowered for pattern in NOISE_TEXT_PATTERNS):
            continue
        # Drop menu/link-list style lines with many separators and little prose.
        if clean.count("|") >= 3 or clean.count("›") >= 3:
            continue
        seen.add(lowered)
        lines.append(clean)
    return "\n".join(lines)[:50000]


def score_extracted_text(text: str) -> float:
    words = text.split()
    if not words:
        return 0
    sentence_marks = text.count(".") + text.count("?") + text.count("!")
    linkish = len([word for word in words if word.startswith(("http://", "https://", "www."))])
    avg_word_len = sum(len(word) for word in words) / max(len(words), 1)
    return len(words) + sentence_marks * 15 + avg_word_len * 3 - linkish * 20


class ScrapeRunner:
    def __init__(self, settings: Settings, repo: ScraperRepository):
        self.settings = settings
        self.repo = repo

    async def run(self, payload) -> dict:
        url = payload.target_url
        domain = domain_for(url)
        if not await robots_allowed(url, self.settings):
            raise ScraperError("robots_disallowed", "robots.txt disallows scraping this URL.", 403, {"target_url": url})
        wait_seconds = await self.repo.wait_for_domain_rate_limit(domain, self.settings.per_domain_delay_seconds)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        crawl_result = await crawl_url(url, self.settings)
        if crawl_result.get("success") is False:
            raise ScraperError("crawl_failed", crawl_result.get("error_message") or "Crawl4AI failed to crawl the URL.", 502)
        document = {
            "event_id": payload.event_id,
            "account_id": payload.account_id,
            "requested_by_user_id": payload.requested_by_user_id,
            "target_url": url,
            "domain": domain,
            "job_type": payload.job_type,
            "metadata": payload.metadata,
            "status": "completed",
            "crawler": "crawl4ai" if not crawl_result.get("crawler_fallback") else crawl_result.get("crawler_fallback"),
            "raw": crawl_result,
            "created_at": datetime.now(timezone.utc),
        }
        document_id = await self.repo.store_document(as_jsonable(document))
        return {"document_id": document_id, "document": document}
