"""
test_fetch_official_announcements.py — fetch_official_announcements 單元測試

測試重點：
- 支援的幣種正確分派到對應來源
- 不支援的幣種回傳空列表
- RSS 解析（RSS 2.0 與 Atom 格式）
- GitHub releases 解析
- 網路錯誤時不崩潰，回傳空列表
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 將 lambda 目錄加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from tools.news import (
    _OFFICIAL_SOURCES,
    _fetch_github_releases,
    _fetch_rss_feed,
    _parse_rss_entries,
    fetch_official_announcements,
)


# ---- _parse_rss_entries 測試 ----


class TestParseRssEntries:
    """RSS/Atom XML 解析測試"""

    def test_rss2_format(self):
        """RSS 2.0 格式能正確解析 title, pubDate, link"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Bitcoin Blog</title>
            <item>
              <title>Bitcoin Core 28.0 Released</title>
              <pubDate>Mon, 01 Jul 2026 12:00:00 GMT</pubDate>
              <link>https://bitcoin.org/en/release/28.0</link>
            </item>
            <item>
              <title>Security Advisory</title>
              <pubDate>Sun, 15 Jun 2026 10:00:00 GMT</pubDate>
              <link>https://bitcoin.org/en/advisory/2026-06</link>
            </item>
          </channel>
        </rss>
        """
        result = _parse_rss_entries(xml, "bitcoin.org Blog")

        assert len(result) == 2
        assert result[0]["title"] == "Bitcoin Core 28.0 Released"
        assert result[0]["published_at"] == "Mon, 01 Jul 2026 12:00:00 GMT"
        assert result[0]["url"] == "https://bitcoin.org/en/release/28.0"
        assert result[0]["source_name"] == "bitcoin.org Blog"

    def test_atom_format(self):
        """Atom 格式能正確解析"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Ethereum Blog</title>
          <entry>
            <title>Pectra Upgrade Announcement</title>
            <published>2026-06-20T14:00:00Z</published>
            <link href="https://blog.ethereum.org/2026/06/pectra"/>
          </entry>
        </feed>
        """
        result = _parse_rss_entries(xml, "Ethereum Foundation Blog")

        assert len(result) == 1
        assert result[0]["title"] == "Pectra Upgrade Announcement"
        assert result[0]["published_at"] == "2026-06-20T14:00:00Z"
        assert result[0]["url"] == "https://blog.ethereum.org/2026/06/pectra"
        assert result[0]["source_name"] == "Ethereum Foundation Blog"

    def test_invalid_xml_returns_empty(self):
        """無效的 XML 回傳空列表不崩潰"""
        result = _parse_rss_entries("not xml at all <><>", "test")
        assert result == []

    def test_empty_xml_returns_empty(self):
        """空的 feed 回傳空列表"""
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Empty</title></channel></rss>
        """
        result = _parse_rss_entries(xml, "test")
        assert result == []

    def test_max_10_entries(self):
        """最多只取 10 筆"""
        items = "\n".join(
            f"<item><title>Item {i}</title><pubDate>date</pubDate><link>url</link></item>"
            for i in range(15)
        )
        xml = f"""<?xml version="1.0"?>
        <rss version="2.0"><channel>{items}</channel></rss>
        """
        result = _parse_rss_entries(xml, "test")
        assert len(result) == 10

    def test_skips_entries_without_title(self):
        """沒有 title 的項目會被跳過"""
        xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title></title>
              <pubDate>date</pubDate>
              <link>url</link>
            </item>
            <item>
              <title>Valid Title</title>
              <pubDate>date2</pubDate>
              <link>url2</link>
            </item>
          </channel>
        </rss>
        """
        result = _parse_rss_entries(xml, "test")
        assert len(result) == 1
        assert result[0]["title"] == "Valid Title"


# ---- _fetch_github_releases 測試 ----


class TestFetchGithubReleases:
    """GitHub releases API 呼叫測試"""

    @patch("tools.news.requests.get")
    def test_success(self, mock_get):
        """成功取得 GitHub releases"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "name": "v28.0",
                "tag_name": "v28.0",
                "published_at": "2026-07-01T12:00:00Z",
                "html_url": "https://github.com/bitcoin/bitcoin/releases/tag/v28.0",
            },
            {
                "name": "",
                "tag_name": "v27.1",
                "published_at": "2026-05-15T10:00:00Z",
                "html_url": "https://github.com/bitcoin/bitcoin/releases/tag/v27.1",
            },
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        config = {"owner": "bitcoin", "repo": "bitcoin", "source_name": "Bitcoin Core"}
        result = _fetch_github_releases(config)

        assert len(result) == 2
        assert result[0]["title"] == "v28.0"
        assert result[1]["title"] == "v27.1"  # falls back to tag_name
        assert result[0]["source_name"] == "Bitcoin Core"

    @patch("tools.news.requests.get")
    def test_network_error_returns_empty(self, mock_get):
        """網路錯誤回傳空列表"""
        mock_get.side_effect = Exception("Connection timeout")

        config = {"owner": "bitcoin", "repo": "bitcoin", "source_name": "Bitcoin Core"}
        result = _fetch_github_releases(config)
        assert result == []


# ---- _fetch_rss_feed 測試 ----


class TestFetchRssFeed:
    """RSS feed HTTP 呼叫測試"""

    @patch("tools.news.requests.get")
    def test_success(self, mock_get):
        """成功取得 RSS feed"""
        mock_resp = MagicMock()
        mock_resp.text = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Test News</title>
              <pubDate>Mon, 01 Jul 2026 12:00:00 GMT</pubDate>
              <link>https://example.com/news</link>
            </item>
          </channel>
        </rss>
        """
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        config = {"url": "https://example.com/rss.xml", "source_name": "Test Blog"}
        result = _fetch_rss_feed(config)

        assert len(result) == 1
        assert result[0]["title"] == "Test News"

    @patch("tools.news.requests.get")
    def test_http_error_returns_empty(self, mock_get):
        """HTTP 錯誤回傳空列表"""
        mock_get.side_effect = Exception("404 Not Found")

        config = {"url": "https://example.com/rss.xml", "source_name": "Test Blog"}
        result = _fetch_rss_feed(config)
        assert result == []


# ---- fetch_official_announcements 整合測試 ----


class TestFetchOfficialAnnouncements:
    """fetch_official_announcements 主函式測試"""

    def test_supported_symbols_have_sources(self):
        """所有支援的幣種都有對應的來源設定"""
        for symbol in ["BTC", "ETH", "SOL", "BNB", "XRP"]:
            assert symbol in _OFFICIAL_SOURCES
            sources = _OFFICIAL_SOURCES[symbol]
            assert "rss" in sources
            assert "github" in sources
            assert len(sources["rss"]) > 0
            assert len(sources["github"]) > 0

    @patch("tools.news._fetch_github_releases")
    @patch("tools.news._fetch_rss_feed")
    def test_combines_rss_and_github(self, mock_rss, mock_github):
        """正確合併 RSS 與 GitHub 結果"""
        mock_rss.return_value = [
            {"title": "Blog Post", "published_at": "2026-07-01", "url": "u1", "source_name": "Blog"}
        ]
        mock_github.return_value = [
            {"title": "Release v1", "published_at": "2026-07-02", "url": "u2", "source_name": "GH"}
        ]

        result = fetch_official_announcements("BTC")

        assert len(result) == 2
        assert result[0]["title"] == "Blog Post"
        assert result[1]["title"] == "Release v1"

    @patch("tools.news._fetch_github_releases")
    @patch("tools.news._fetch_rss_feed")
    def test_unsupported_symbol_returns_empty(self, mock_rss, mock_github):
        """不支援的幣種回傳空列表"""
        result = fetch_official_announcements("DOGE")
        assert result == []
        mock_rss.assert_not_called()
        mock_github.assert_not_called()

    @patch("tools.news._fetch_github_releases")
    @patch("tools.news._fetch_rss_feed")
    def test_all_sources_fail_returns_empty(self, mock_rss, mock_github):
        """所有來源都失敗時回傳空列表不崩潰"""
        mock_rss.return_value = []
        mock_github.return_value = []

        result = fetch_official_announcements("ETH")
        assert result == []

    @patch("tools.news._fetch_github_releases")
    @patch("tools.news._fetch_rss_feed")
    def test_return_format(self, mock_rss, mock_github):
        """回傳格式正確：每筆包含 title, published_at, url, source_name"""
        mock_rss.return_value = [
            {
                "title": "Upgrade Notice",
                "published_at": "2026-07-01T00:00:00Z",
                "url": "https://example.com/upgrade",
                "source_name": "ETH Blog",
            }
        ]
        mock_github.return_value = []

        result = fetch_official_announcements("ETH")

        assert len(result) == 1
        entry = result[0]
        assert "title" in entry
        assert "published_at" in entry
        assert "url" in entry
        assert "source_name" in entry
