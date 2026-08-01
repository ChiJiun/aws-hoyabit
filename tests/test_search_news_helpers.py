"""Test search_news helper functions and main function behavior."""

import sys
sys.path.insert(0, "lambda")

from unittest.mock import patch, MagicMock
from tools.news import (
    search_news,
    _extract_domain_family,
    _title_similarity,
    _mark_duplicate_sources,
)


def test_extract_domain_family():
    assert _extract_domain_family("www.coindesk.com") == "coindesk"
    assert _extract_domain_family("blog.binance.com") == "binance"
    assert _extract_domain_family("cointelegraph.com") == "cointelegraph"
    assert _extract_domain_family("") == ""
    assert _extract_domain_family(None) == ""


def test_title_similarity():
    # Identical titles
    sim = _title_similarity("Bitcoin hits new high in 2024", "Bitcoin hits new high in 2024")
    assert sim == 1.0

    # Empty inputs
    assert _title_similarity("", "test") == 0.0
    assert _title_similarity("test", "") == 0.0

    # Similar titles (same words with minor additions)
    sim = _title_similarity(
        "Bitcoin price rises sharply today",
        "Bitcoin price rises sharply today afternoon",
    )
    assert sim > 0.6


def test_mark_duplicate_sources():
    items = [
        {"title": "BTC up 5%", "domain": "coindesk.com"},
        {"title": "BTC up 5%", "domain": "cointelegraph.com"},
        {"title": "ETH staking update", "domain": "news.bitcoin.com"},
    ]
    result = _mark_duplicate_sources(items)
    assert all("source_family" in item for item in result)
    # First two items should share the same source_family due to title similarity
    assert result[0]["source_family"] == result[1]["source_family"]


def test_search_news_returns_graceful_response_on_all_feeds_failing():
    """Property 8: RSS feed failures don't prevent partial results — when all fail,
    still returns a valid C1 success response (empty items, no error raised)."""
    with patch("tools.news.requests.get") as mock_get:
        mock_get.side_effect = Exception("Network error")
        with patch("tools.news.fetch_official_announcements") as mock_official:
            mock_official.return_value = []
            result = search_news("BTC", 7, "test claim")
            assert isinstance(result, dict)
            # New behavior: graceful degradation returns success format with 0 items
            assert "source" in result
            assert "content_reference" in result
            assert "summary" in result
            assert "raw" in result
            # Should not raise — that's the key property
            assert result["content_reference"].get("total_count", 0) == 0


def test_search_news_returns_unified_format_on_success():
    """Property 2: successful return contains raw, source, content_reference, summary."""
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Test</title>
    <item><title>Bitcoin breaks 100k</title>
    <pubDate>2026-07-01T10:00:00Z</pubDate>
    <link>https://example.com/btc-100k</link></item>
    </channel></rss>"""

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = rss_xml
    mock_response.raise_for_status = MagicMock()

    with patch("tools.news.requests.get") as mock_get:
        mock_get.return_value = mock_response
        with patch("tools.news.fetch_official_announcements") as mock_official:
            mock_official.return_value = []
            result = search_news("BTC", 7, "test claim")

    assert isinstance(result, dict)
    assert "raw" in result
    assert "source" in result
    assert "content_reference" in result
    assert "summary" in result
    assert "error" not in result


def test_search_news_marks_duplicates_in_summary():
    """Requirement 9.4: duplicate source family reports are annotated."""
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Test</title>
    <item><title>Major Bitcoin ETF approved by SEC</title>
    <pubDate>2026-07-01T10:00:00Z</pubDate>
    <link>https://coindesk.com/btc-etf</link></item>
    <item><title>Major Bitcoin ETF approved by SEC today</title>
    <pubDate>2026-07-01T10:05:00Z</pubDate>
    <link>https://cointelegraph.com/btc-etf</link></item>
    </channel></rss>"""

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = rss_xml
    mock_response.raise_for_status = MagicMock()

    with patch("tools.news.requests.get") as mock_get:
        mock_get.return_value = mock_response
        with patch("tools.news.fetch_official_announcements") as mock_official:
            mock_official.return_value = []
            result = search_news("BTC", 7, "test claim")

    assert "error" not in result
    # The summary should contain a duplicate warning
    assert "來源家族" in result["summary"] or "通稿" in result["summary"]


if __name__ == "__main__":
    test_extract_domain_family()
    print("test_extract_domain_family: PASSED")

    test_title_similarity()
    print("test_title_similarity: PASSED")

    test_mark_duplicate_sources()
    print("test_mark_duplicate_sources: PASSED")

    test_search_news_returns_graceful_response_on_all_feeds_failing()
    print("test_search_news_returns_graceful_response_on_all_feeds_failing: PASSED")

    test_search_news_returns_unified_format_on_success()
    print("test_search_news_returns_unified_format_on_success: PASSED")

    test_search_news_marks_duplicates_in_summary()
    print("test_search_news_marks_duplicates_in_summary: PASSED")

    print("\nAll tests passed!")
