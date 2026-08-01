"""
prediction.py — 預測市場工具

資料來源：Polymarket Gamma API（免鑰、免認證）

設計考量：
- Polymarket 是目前最大的加密預測市場，用真金白銀定價事件機率
- 預測市場的共識定價可與現貨走勢比對，發現「價格未反映的預期」
- 例如 ETH ETF 批准機率大幅上升但 ETH 價格未動 → 潛在上行催化
- Gamma API 提供事件搜尋與市場數據，完全免費
- 搜尋策略：先用關鍵字搜尋，無結果則 fallback 到 crypto tag 篩選
"""

import json
import time
import warnings
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import evidence

# ---- 常數 ----
_GAMMA_BASE = "https://gamma-api.polymarket.com"
_TIMEOUT = 30
_HEADERS = {"User-Agent": "HoyabitAgent/1.0"}
_MAX_DISPLAY_EVENTS = 5


def _get_session():
    """建立帶重試機制的 requests Session，處理 SSL/網路暫時問題。"""
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(_HEADERS)
    return session


def _robust_get(url, timeout=_TIMEOUT):
    """帶 SSL fallback 的 GET 請求。

    策略：
    1. 先用正常 SSL 驗證嘗試
    2. SSL 失敗時 fallback 到 verify=False（某些地區 Polymarket 的 SSL 憑證有問題）
    回傳 Response 物件，失敗則拋出原始例外。
    """
    session = _get_session()
    try:
        resp = session.get(url, timeout=timeout)
        return resp
    except requests.exceptions.SSLError:
        # SSL 失敗，嘗試關閉驗證（可能是地區封鎖或自簽憑證）
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        try:
            resp = session.get(url, timeout=timeout, verify=False)
            # 檢查是否為 ISP 封鎖頁面（回傳 404 或含有封鎖關鍵字）
            if resp.status_code == 404 or "封鎖" in resp.text[:500] or "blocked" in resp.text[:500].lower():
                raise requests.exceptions.ConnectionError(
                    f"Polymarket API 不可用（可能為地區網路限制）: HTTP {resp.status_code}"
                )
            return resp
        except requests.exceptions.SSLError as e2:
            raise e2


def get_prediction_market(keywords, related_claim):
    """從 Polymarket 查詢加密相關事件市場的價格與成交量。

    搜尋策略：
    1. 先以 keywords 做 title_contains 搜尋
    2. 若無結果，fallback 到 crypto tag 篩選
    從結果中提取事件標題、市場定價機率、成交量等資訊。

    Args:
        keywords: 搜尋關鍵字（如 "bitcoin", "ETH ETF", "crypto regulation"）
        related_claim: Agent 說明取數目的

    Returns:
        Contract C1 dict or error dict
    """
    # 功能：查詢 Polymarket 預測市場加密相關事件
    # 步驟：
    #   1. 嘗試 keyword 搜尋
    #   2. 無結果時 fallback 到 crypto tag
    #   3. 解析事件資料（title、outcomePrices、volume）
    #   4. 組裝 summary 與 content_reference
    # 回傳：Contract C1 格式 dict

    source_url = f"{_GAMMA_BASE}/events?active=true&closed=false&limit=10&title_contains={keywords}"
    endpoints_called = []
    start_time = time.time()

    try:
        # 步驟 1：嘗試 keyword 搜尋
        keyword_url = f"{_GAMMA_BASE}/events?active=true&closed=false&limit=10&title_contains={keywords}"
        endpoints_called.append(keyword_url)

        resp = _robust_get(keyword_url)
        resp.raise_for_status()
        events_data = resp.json()

        # 步驟 2：若無結果，fallback 到 crypto tag
        if not events_data:
            fallback_url = f"{_GAMMA_BASE}/events?tag=crypto&active=true&closed=false&limit=10"
            endpoints_called.append(fallback_url)
            source_url = fallback_url

            resp = _robust_get(fallback_url)
            resp.raise_for_status()
            events_data = resp.json()

        # 確保 events_data 是 list
        if not isinstance(events_data, list):
            events_data = []

        # 步驟 3：解析事件資料
        parsed_events = []
        for event in events_data:
            parsed = _parse_event(event)
            if parsed:
                parsed_events.append(parsed)

        # 步驟 4：組裝 content_reference
        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        content_reference = {
            "endpoints_called": endpoints_called,
            "query_keywords": keywords,
            "events": parsed_events[:_MAX_DISPLAY_EVENTS],
            "total_events_found": len(parsed_events),
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
        }

        # 步驟 5：組裝 summary
        summary = _build_summary(keywords, parsed_events)

        # 記錄成功
        evidence.log_execution_step(
            tool_name="get_prediction_market",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"keywords='{keywords}', found {len(parsed_events)} events",
        )

        return {
            "raw": events_data,
            "source": source_url,
            "content_reference": content_reference,
            "summary": summary,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="get_prediction_market",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[get_prediction_market] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def _parse_event(event):
    """解析單一事件物件，提取標題、機率、成交量等。

    Args:
        event: Gamma API 回傳的事件 dict

    Returns:
        解析後的 dict 或 None（若事件無效）
    """
    # 功能：從 Gamma API 事件物件中提取關鍵欄位
    # 回傳：標準化的事件 dict

    if not isinstance(event, dict):
        return None

    title = event.get("title", "")
    if not title:
        return None

    # 解析 outcomePrices（可能是 JSON string 或已是 list）
    outcome_price = _extract_outcome_price(event)

    # 提取成交量（可能是字串或數字）
    volume_raw = event.get("volume", 0)
    try:
        volume_usd = float(volume_raw) if volume_raw else 0.0
    except (ValueError, TypeError):
        volume_usd = 0.0

    # 提取其他欄位
    slug = event.get("slug", "")
    end_date = event.get("endDate", "")
    liquidity_raw = event.get("liquidity", 0)
    try:
        liquidity = float(liquidity_raw) if liquidity_raw else 0.0
    except (ValueError, TypeError):
        liquidity = 0.0

    return {
        "title": title,
        "slug": slug,
        "outcome_price": outcome_price,
        "volume_usd": volume_usd,
        "liquidity_usd": liquidity,
        "end_date": end_date,
    }


def _extract_outcome_price(event):
    """從事件物件中提取主要結果的機率定價。

    Polymarket 的 outcomePrices 可能是：
    - JSON string: '["0.42","0.58"]'（Yes/No 機率）
    - list: [0.42, 0.58]
    - 或不存在

    回傳 Yes 結果的機率（float），若無法解析回傳 None。
    """
    # 嘗試 outcomePrices 欄位
    outcome_prices = event.get("outcomePrices", None)

    if outcome_prices is not None:
        # 若為 JSON string，嘗試解析
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except (json.JSONDecodeError, ValueError):
                return None

        # 取第一個值（Yes 的機率）
        if isinstance(outcome_prices, list) and len(outcome_prices) > 0:
            try:
                return float(outcome_prices[0])
            except (ValueError, TypeError):
                return None

    # 備用：嘗試 outcomes 欄位（某些 API 版本）
    outcomes = event.get("outcomes", None)
    if outcomes and isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _build_summary(keywords, parsed_events):
    """組裝給模型看的精簡摘要。

    格式範例：
    Polymarket 加密事件市場（關鍵字: bitcoin）：
    - "BTC $150K by Dec 2026": 機率 42%, 成交量 $2.1M
    - "ETH ETF approved Q3 2026": 機率 78%, 成交量 $890K
    （共找到 N 個相關事件市場）
    """
    # 功能：產生精簡的事件市場摘要
    # 回傳：不超過 2000 字元的摘要字串

    if not parsed_events:
        return f"Polymarket 加密事件市場（關鍵字: {keywords}）：未找到相關活躍事件市場。"

    lines = [f"Polymarket 加密事件市場（關鍵字: {keywords}）："]

    for event in parsed_events[:_MAX_DISPLAY_EVENTS]:
        title = event["title"]
        # 截斷過長的標題
        if len(title) > 60:
            title = title[:57] + "..."

        price = event.get("outcome_price")
        volume = event.get("volume_usd", 0)

        # 格式化機率
        if price is not None:
            prob_str = f"機率 {price * 100:.0f}%"
        else:
            prob_str = "機率 N/A"

        # 格式化成交量
        vol_str = _format_volume(volume)

        lines.append(f'- "{title}": {prob_str}, 成交量 {vol_str}')

    lines.append(f"（共找到 {len(parsed_events)} 個相關事件市場）")

    summary = "\n".join(lines)

    # 控制摘要長度上限
    if len(summary) > 2000:
        summary = summary[:1997] + "..."

    return summary


def _format_volume(volume_usd):
    """將成交量格式化為可讀字串。"""
    if volume_usd >= 1_000_000:
        return f"${volume_usd / 1_000_000:.1f}M"
    elif volume_usd >= 1_000:
        return f"${volume_usd / 1_000:.1f}K"
    elif volume_usd > 0:
        return f"${volume_usd:.0f}"
    else:
        return "$0"
