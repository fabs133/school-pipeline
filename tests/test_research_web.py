"""Tests for schulpipeline.research.web — DiskCache and search utilities."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from schulpipeline.research.web import DiskCache, _ddg_search, _scrape_page

# ---------------------------------------------------------------------------
# DiskCache tests
# ---------------------------------------------------------------------------


def test_disk_cache_put_get(tmp_path):
    """Round-trip: put then get returns the same data."""
    cache = DiskCache(tmp_path / "cache")
    data = [{"url": "https://example.com", "title": "Example", "snippet": "A page"}]
    cache.put("test query", data)
    result = cache.get("test query")
    assert result == data


def test_disk_cache_miss(tmp_path):
    """Getting a non-existent key returns None."""
    cache = DiskCache(tmp_path / "cache")
    assert cache.get("nonexistent") is None


def test_disk_cache_expiry(tmp_path):
    """Expired cache entries return None."""
    cache = DiskCache(tmp_path / "cache")
    data = [{"url": "https://example.com"}]
    cache.put("test query", data)

    # Manually backdate the timestamp
    key = cache._key("test query")
    path = cache.dir / f"{key}.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    content["ts"] = time.time() - 90000  # > 24h ago
    path.write_text(json.dumps(content), encoding="utf-8")

    assert cache.get("test query") is None


# ---------------------------------------------------------------------------
# DDG search mock tests
# ---------------------------------------------------------------------------


def test_search_ddg_mock():
    """Mock requests.post to verify DDG search parsing."""
    mock_html = """
    <html><body>
    <div class="result__body">
        <h2 class="result__title"><a href="https://example.com">Example Title</a></h2>
        <span class="result__snippet">An example snippet</span>
    </div>
    </body></html>
    """
    mock_response = MagicMock()
    mock_response.text = mock_html
    mock_response.raise_for_status = MagicMock()

    with patch("schulpipeline.research.web.requests.post", return_value=mock_response) as mock_post:
        results = _ddg_search("test query", max_results=5)
        mock_post.assert_called_once()
        # Verify timeout is passed
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs.get("timeout") == 10 or call_kwargs[1].get("timeout") == 10

    assert len(results) == 1
    assert results[0]["title"] == "Example Title"
    assert results[0]["url"] == "https://example.com"


# ---------------------------------------------------------------------------
# Scrape page mock tests
# ---------------------------------------------------------------------------


def test_scrape_page_mock():
    """Mock requests.get to verify page scraping."""
    mock_html = """
    <html><body>
    <main><p>Main content here</p></main>
    </body></html>
    """
    mock_response = MagicMock()
    mock_response.text = mock_html
    mock_response.raise_for_status = MagicMock()

    with patch("schulpipeline.research.web.requests.get", return_value=mock_response) as mock_get:
        text = _scrape_page("https://example.com")
        mock_get.assert_called_once()
        # Verify timeout is passed
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs.get("timeout") == 10 or call_kwargs[1].get("timeout") == 10

    assert "Main content here" in text


def test_scrape_page_failure():
    """Scrape returns empty string on request failure."""
    import requests as req

    with patch("schulpipeline.research.web.requests.get", side_effect=req.ConnectionError("fail")):
        text = _scrape_page("https://example.com")
    assert text == ""
