"""Web search via DuckDuckGo + page scraping with disk caching."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("schulpipeline.research.web")

DDG_HTML_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "Mozilla/5.0 (compatible; schulpipeline/0.1)"


@dataclass
class SearchResult:
    """A single search result with extracted text."""
    url: str
    title: str
    snippet: str
    text: str = ""
    quality: str = "low"  # low | medium | high


class DiskCache:
    """Simple file-based cache for search results."""

    def __init__(self, cache_dir: str | Path):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _key(self, query: str) -> str:
        return hashlib.sha256(query.encode()).hexdigest()[:16]

    def get(self, query: str) -> list[dict] | None:
        path = self.dir / f"{self._key(query)}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Expire after 24h
            if time.time() - data.get("ts", 0) > 86400:
                path.unlink(missing_ok=True)
                return None
            return data.get("results", [])
        except (json.JSONDecodeError, KeyError):
            return None

    def put(self, query: str, results: list[dict]) -> None:
        path = self.dir / f"{self._key(query)}.json"
        data = {"ts": time.time(), "query": query, "results": results}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _ddg_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search DuckDuckGo HTML endpoint. Returns list of {title, url, snippet}."""
    try:
        resp = requests.post(
            DDG_HTML_URL,
            data={"q": query, "b": ""},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"DDG search failed for '{query}': {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for result_div in soup.select(".result__body")[:max_results]:
        title_el = result_div.select_one(".result__title a")
        snippet_el = result_div.select_one(".result__snippet")
        if not title_el:
            continue

        url = title_el.get("href", "")
        # DDG wraps URLs — extract the actual URL
        if "uddg=" in url:
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(url)
            actual = parse_qs(parsed.query).get("uddg", [""])[0]
            url = actual

        results.append({
            "title": title_el.get_text(strip=True),
            "url": url,
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })

    logger.debug(f"DDG: '{query}' → {len(results)} results")
    return results


def _scrape_page(url: str, max_chars: int = 2000) -> str:
    """Fetch a page and extract main text content."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.debug(f"Scrape failed for {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove script/style/nav elements
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # Try to find main content
    main = soup.select_one("main") or soup.select_one("article") or soup.body
    if not main:
        return ""

    text = main.get_text(separator="\n", strip=True)
    # Collapse blank lines
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    text = "\n".join(lines)

    return text[:max_chars]


def _assess_quality(text: str, snippet: str) -> str:
    """Simple quality heuristic based on text length."""
    if len(text) > 500:
        return "high"
    if len(text) > 100 or len(snippet) > 50:
        return "medium"
    return "low"


async def search_and_extract(
    query: str,
    max_results: int = 3,
    cache: DiskCache | None = None,
) -> list[SearchResult]:
    """Search DDG and extract text from top results."""

    # Check cache
    if cache:
        cached = cache.get(query)
        if cached is not None:
            logger.debug(f"Cache hit for '{query}'")
            return [SearchResult(**r) for r in cached]

    # Run blocking search in thread
    raw_results = await asyncio.to_thread(_ddg_search, query, max_results)

    results: list[SearchResult] = []
    for raw in raw_results:
        url = raw["url"]
        if not url:
            continue

        text = await asyncio.to_thread(_scrape_page, url)
        quality = _assess_quality(text, raw["snippet"])

        results.append(SearchResult(
            url=url,
            title=raw["title"],
            snippet=raw["snippet"],
            text=text,
            quality=quality,
        ))

    # Cache results
    if cache and results:
        cache.put(query, [
            {"url": r.url, "title": r.title, "snippet": r.snippet,
             "text": r.text, "quality": r.quality}
            for r in results
        ])

    return results
