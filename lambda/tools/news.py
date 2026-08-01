"""
news.py — 新聞與官方公告工具

資料來源：Google News RSS、媒體 RSS（CoinDesk / The Block / Cointelegraph）、
         各專案官方部落格 RSS、GitHub releases
"""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests
from urllib.parse import urlparse, quote_plus

import evidence

# ---- 幣種搜尋詞對照表（Google News RSS 用）----
_SYMBOL_SEARCH_TERMS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "bnb chain",
    "XRP": "ripple XRP",
}

# ---- 媒體 RSS 白名單 ----
_MEDIA_RSS_FEEDS = [
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source_name": "CoinDesk", "channel": "media_rss"},
    {"url": "https://www.theblock.co/rss.xml", "source_name": "The Block", "channel": "media_rss"},
    {"url": "https://cointelegraph.com/rss", "source_name": "Cointelegraph", "channel": "media_rss"},
]

# ---- 官方來源對照表 ----
# 每個幣種對應其官方部落格 RSS feed 與 GitHub releases repo
_OFFICIAL_SOURCES = {
    "BTC": {
        "rss": [
            {
                "url": "https://bitcoin.org/en/rss/blog.xml",
                "source_name": "bitcoin.org Blog",
            },
        ],
        "github": [
            {
                "owner": "bitcoin",
                "repo": "bitcoin",
                "source_name": "Bitcoin Core GitHub Releases",
            },
        ],
    },
    "ETH": {
        "rss": [
            {
                "url": "https://blog.ethereum.org/feed.xml",
                "source_name": "Ethereum Foundation Blog",
            },
        ],
        "github": [
            {
                "owner": "ethereum",
                "repo": "go-ethereum",
                "source_name": "go-ethereum GitHub Releases",
            },
        ],
    },
    "SOL": {
        "rss": [
            {
                "url": "https://solana.com/news/rss.xml",
                "source_name": "Solana Blog",
            },
        ],
        "github": [
            {
                "owner": "solana-labs",
                "repo": "solana",
                "source_name": "Solana GitHub Releases",
            },
        ],
    },
    "BNB": {
        "rss": [
            {
                "url": "https://www.bnbchain.org/en/blog/rss.xml",
                "source_name": "BNB Chain Blog",
            },
        ],
        "github": [
            {
                "owner": "bnb-chain",
                "repo": "bsc",
                "source_name": "BNB Chain GitHub Releases",
            },
        ],
    },
    "XRP": {
        "rss": [
            {
                "url": "https://xrpl.org/blog/feed.xml",
                "source_name": "XRPL Blog",
            },
        ],
        "github": [
            {
                "owner": "XRPLF",
                "repo": "rippled",
                "source_name": "rippled GitHub Releases",
            },
        ],
    },
}

# GitHub public API base URL
_GITHUB_API_BASE = "https://api.github.com"


def search_news(symbol, lookback_days, related_claim, keywords=None):
    """查詢指定幣種在近期的新聞、官方公告與監管消息。

    步驟：
      1. 從 Google News RSS 取得該幣種的新聞聚合
      2. 從媒體 RSS 白名單（CoinDesk / The Block / Cointelegraph）取得一手報導
      3. 呼叫 fetch_official_announcements() 取得官方公告 + GitHub releases
      4. 合併、去重、依發布時間排序
    content_reference 應包含：標題、發布時間、原文網址、引用片段。
    注意：一則通稿常被多家媒體轉載，摘要中應標註哪些來自同一來源家族，
         避免模型誤判為「多源共識」。
    回傳：統一格式 dict（Contract C1）
    """
    # 建構 Google News RSS URL 作為 source 標示
    search_term = _SYMBOL_SEARCH_TERMS.get(symbol, symbol.lower())
    query = f"{search_term}+crypto"
    if keywords:
        kw_str = "+".join(keywords) if isinstance(keywords, list) else keywords
        query += f"+{kw_str}"
    google_news_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en&gl=US&ceid=US:en"

    source_url = google_news_url
    start_time = time.time()

    try:
        news_items = []

        # 1. Google News RSS
        try:
            resp = requests.get(
                google_news_url,
                timeout=30,
                headers={"User-Agent": "HoyabitAgent/1.0"},
            )
            resp.raise_for_status()
            google_entries = _parse_rss_entries(resp.text, "Google News")
            for item in google_entries:
                item["channel"] = "google_news"
            news_items.extend(google_entries)
        except Exception:
            pass  # Google News 失敗 → skip，繼續其他來源

        # 2. 媒體 RSS 白名單（每個 feed 獨立 try/except）
        for feed_config in _MEDIA_RSS_FEEDS:
            try:
                resp = requests.get(
                    feed_config["url"],
                    timeout=30,
                    headers={"User-Agent": "HoyabitAgent/1.0"},
                )
                resp.raise_for_status()
                media_entries = _parse_rss_entries(resp.text, feed_config["source_name"])
                for item in media_entries:
                    item["channel"] = feed_config["channel"]
                news_items.extend(media_entries)
            except Exception:
                pass  # 單一 feed 失敗 → skip

        # 3. 官方公告 + GitHub releases
        official_items = fetch_official_announcements(symbol)
        for item in official_items:
            # 根據 source_name 判斷是 official_rss 還是 github_release
            if "GitHub" in item.get("source_name", ""):
                item["channel"] = "github_release"
            else:
                item["channel"] = "official_rss"
            news_items.append(item)

        # 為所有 items 補上 domain 欄位
        for item in news_items:
            if not item.get("domain"):
                if item.get("url"):
                    try:
                        item["domain"] = urlparse(item["url"]).netloc
                    except Exception:
                        item["domain"] = ""
                else:
                    item["domain"] = ""

        # 4. 標註同一來源家族的重複報導
        news_items = _mark_duplicate_sources(news_items)

        # 5. 依發布時間排序（最新的在前）
        news_items.sort(key=lambda x: x.get("published_at", ""), reverse=True)

        # 6. 組裝 content_reference
        content_reference = {
            "items": [
                {
                    "title": item.get("title", ""),
                    "published_at": item.get("published_at", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("title", "")[:100],
                    "channel": item.get("channel", ""),
                }
                for item in news_items[:20]  # 最多回傳 20 筆
            ],
            "total_count": len(news_items),
            "symbol": symbol,
        }

        # 7. 組裝摘要
        # 統計來源家族重複
        duplicate_groups = {}
        for item in news_items:
            family = item.get("source_family", "")
            if family:
                duplicate_groups.setdefault(family, []).append(item.get("title", ""))

        duplicate_warnings = []
        for family, titles in duplicate_groups.items():
            if len(titles) > 1:
                duplicate_warnings.append(
                    f"⚠️ {len(titles)} 篇來自同一來源家族「{family}」，可能為同一通稿轉載"
                )

        unique_source_count = len(set(
            item.get("domain", "") for item in news_items if item.get("domain")
        ))
        top_headlines = [item.get("title", "") for item in news_items[:3]]

        # 統計各管道數量
        channel_counts = {}
        for item in news_items:
            ch = item.get("channel", "unknown")
            channel_counts[ch] = channel_counts.get(ch, 0) + 1

        channel_summary = "、".join(
            f"{ch} {cnt} 篇" for ch, cnt in channel_counts.items()
        )

        summary_parts = [
            f"{symbol} 近期新聞：共 {len(news_items)} 筆（{channel_summary}），"
            f"來自 {unique_source_count} 個不同來源。",
        ]
        if top_headlines:
            summary_parts.append(f"主要標題：{'；'.join(top_headlines)}")
        if duplicate_warnings:
            summary_parts.extend(duplicate_warnings)

        summary = "\n".join(summary_parts)

        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="search_news",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"{symbol}: {len(news_items)} news items, {len(duplicate_warnings)} duplicate warnings",
        )

        return {
            "raw": {"items": news_items[:20], "total_fetched": len(news_items)},
            "source": source_url,
            "content_reference": content_reference,
            "summary": summary,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="search_news",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"{symbol}: {type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[search_news] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def _extract_domain_family(domain):
    """從 domain 中提取來源家族名稱。

    例如：
      - 'www.coindesk.com' → 'coindesk'
      - 'blog.binance.com' → 'binance'
      - 'cointelegraph.com' → 'cointelegraph'
    """
    if not domain:
        return ""
    # 移除常見前綴
    parts = domain.lower().replace("www.", "").replace("blog.", "").split(".")
    if len(parts) >= 2:
        return parts[-2]  # 取主域名
    return parts[0] if parts else ""


def _title_similarity(title_a, title_b):
    """簡易標題相似度檢測（基於共同詞彙比例）。"""
    if not title_a or not title_b:
        return 0.0
    words_a = set(title_a.lower().split())
    words_b = set(title_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def _mark_duplicate_sources(news_items):
    """標註來自同一來源家族的重複報導。

    偵測邏輯：
    1. 同一 domain family 的多篇報導
    2. 標題相似度超過閾值的報導（可能是同一通稿被多家轉載）
    """
    # 為每個 item 標註 source_family
    for item in news_items:
        domain = item.get("domain", "")
        item["source_family"] = _extract_domain_family(domain)

    # 偵測標題高度相似的報導，歸入同一家族
    similarity_threshold = 0.6
    for i in range(len(news_items)):
        for j in range(i + 1, len(news_items)):
            sim = _title_similarity(
                news_items[i].get("title", ""),
                news_items[j].get("title", ""),
            )
            if sim >= similarity_threshold:
                # 將後者的 source_family 標記為與前者相同
                family = news_items[i].get("source_family", "") or "similar_content"
                news_items[i]["source_family"] = family
                news_items[j]["source_family"] = family

    return news_items


def _parse_rss_entries(xml_text, source_name):
    """解析 RSS/Atom XML 文字，回傳公告列表。

    支援兩種常見格式：
    - RSS 2.0：<channel><item><title>/<pubDate>/<link>
    - Atom：<feed><entry><title>/<published|updated>/<link href="...">
    """
    announcements = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return announcements

    # Atom namespace
    _ATOM_NS = "{http://www.w3.org/2005/Atom}"

    # 嘗試 RSS 2.0 格式
    items = root.findall(".//item")
    if items:
        for item in items[:10]:  # 只取最近 10 筆
            title = item.findtext("title", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            link = item.findtext("link", "").strip()
            if title:
                announcements.append({
                    "title": title,
                    "published_at": pub_date,
                    "url": link,
                    "source_name": source_name,
                })
        return announcements

    # 嘗試 Atom 格式（帶命名空間或不帶）
    entries = root.findall(f"{_ATOM_NS}entry")
    if not entries:
        entries = root.findall("entry")

    for entry in entries[:10]:
        # title — 嘗試帶 namespace 再嘗試不帶
        title_el = entry.find(f"{_ATOM_NS}title")
        if title_el is None:
            title_el = entry.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        # published date
        pub_el = entry.find(f"{_ATOM_NS}published")
        if pub_el is None:
            pub_el = entry.find(f"{_ATOM_NS}updated")
        if pub_el is None:
            pub_el = entry.find("published")
        if pub_el is None:
            pub_el = entry.find("updated")
        pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

        # link
        link_el = entry.find(f"{_ATOM_NS}link")
        if link_el is None:
            link_el = entry.find("link")
        link = ""
        if link_el is not None:
            link = link_el.get("href", "") or (link_el.text or "").strip()

        if title:
            announcements.append({
                "title": title,
                "published_at": pub_date,
                "url": link,
                "source_name": source_name,
            })

    return announcements


def _fetch_rss_feed(rss_config):
    """從單一 RSS feed URL 取得公告列表。"""
    url = rss_config["url"]
    source_name = rss_config["source_name"]
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "HoyabitAgent/1.0"})
        resp.raise_for_status()
        return _parse_rss_entries(resp.text, source_name)
    except Exception:
        return []


def _fetch_github_releases(github_config):
    """從 GitHub releases API 取得最新版本公告。"""
    owner = github_config["owner"]
    repo = github_config["repo"]
    source_name = github_config["source_name"]
    url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/releases?per_page=5"

    try:
        resp = requests.get(
            url,
            timeout=30,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "HoyabitAgent/1.0",
            },
        )
        resp.raise_for_status()
        releases = resp.json()

        announcements = []
        for release in releases:
            title = release.get("name") or release.get("tag_name", "")
            published_at = release.get("published_at", "")
            html_url = release.get("html_url", "")
            if title:
                announcements.append({
                    "title": title,
                    "published_at": published_at,
                    "url": html_url,
                    "source_name": source_name,
                })
        return announcements
    except Exception:
        return []


def fetch_official_announcements(symbol):
    """抓取專案官方的一手消息（公告、版本發布、重大更新排程）。

    來源：官方部落格 RSS、GitHub releases API。
    為什麼優先抓：官方公告是可信度最高的一手來源，且「已排定的事件」
                 （代幣解鎖、協議升級）往往是判斷市場方向最有力的依據，
                 純看價格與情緒的分析會完全漏掉這一塊。

    Args:
        symbol: 幣種代號（BTC, ETH, SOL, BNB, XRP）

    Returns:
        list[dict]: 公告清單，每筆包含 title, published_at, url, source_name。
                    失敗時回傳空列表。
    """
    start_time = time.time()
    announcements = []

    sources = _OFFICIAL_SOURCES.get(symbol)
    if not sources:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            "fetch_official_announcements",
            "error",
            elapsed_ms,
            note=f"不支援的幣種: {symbol}",
        )
        return []

    # 抓取 RSS feeds
    for rss_config in sources.get("rss", []):
        entries = _fetch_rss_feed(rss_config)
        announcements.extend(entries)

    # 抓取 GitHub releases
    for github_config in sources.get("github", []):
        releases = _fetch_github_releases(github_config)
        announcements.extend(releases)

    elapsed_ms = int((time.time() - start_time) * 1000)
    status = "success" if announcements else "empty"
    evidence.log_execution_step(
        "fetch_official_announcements",
        status,
        elapsed_ms,
        note=f"{symbol}: {len(announcements)} announcements fetched",
    )

    return announcements
