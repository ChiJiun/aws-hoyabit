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


def test_search_news_returns_error_dict_on_failure():
    """Property 12: search_news never raises, returns error dict on failure."""
    with patch("tools.news.requests.get") as mock_get:
        mock_get.side_effect = Exception("Network error")
        result = search_news("BTC", 7, "test claim")
        assert isinstance(result, dict)
        assert "error" in result
        assert "source" in result
        assert "content_reference" in result


def test_search_news_returns_unified_format_on_success():
    """Property 13: successful return contains raw, source, content_reference, summary."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "title": "Bitcoin breaks 100k",
                "published_at": "2026-07-01T10:00:00Z",
                "url": "https://example.com/btc-100k",
                "source": {"title": "CoinDesk", "domain": "coindesk.com"},
            }
        ]
    }
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
    """Requirement 7.3: duplicate source family reports are annotated."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "title": "Major Bitcoin ETF approved by SEC",
                "published_at": "2026-07-01T10:00:00Z",
                "url": "https://coindesk.com/btc-etf",
                "source": {"title": "CoinDesk", "domain": "coindesk.com"},
            },
            {
                "title": "Major Bitcoin ETF approved by SEC today",
                "published_at": "2026-07-01T10:05:00Z",
                "url": "https://cointelegraph.com/btc-etf",
                "source": {"title": "CoinTelegraph", "domain": "cointelegraph.com"},
            },
        ]
    }
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

    test_search_news_returns_error_dict_on_failure()
    print("test_search_news_returns_error_dict_on_failure: PASSED")

    test_search_news_returns_unified_format_on_success()
    print("test_search_news_returns_unified_format_on_success: PASSED")

    test_search_news_marks_duplicates_in_summary()
    print("test_search_news_marks_duplicates_in_summary: PASSED")

    print("\nAll tests passed!")
