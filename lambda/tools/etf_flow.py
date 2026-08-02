"""
etf_flow.py — ETF 資金流向工具

資料來源：SosoValue API（需 SOSOVALUE_API_KEY）

設計考量：
- BTC/ETH 現貨 ETF 每日淨流入/流出是機構資金進出場最直接的指標
- 連續淨流入 = 機構看好、持續建倉；連續淨流出 = 機構減持
- 僅支援 BTC 與 ETH（目前美國市場只有這兩個加密現貨 ETF 類別）
- 所有外部 API 呼叫設 timeout，失敗回傳 error dict，絕不拋出未處理例外
"""

import time
from datetime import datetime, timezone

import requests

import config
import evidence

# ---- API 設定 ----
_BASE_URL = "https://openapi.sosovalue.com/openapi/v1"
_TIMEOUT = 30
_HEADERS_BASE = {"User-Agent": "HoyabitAgent/1.0"}

# ---- 支援的 ETF 類別 ----
_SUPPORTED_SYMBOLS = {"BTC", "ETH"}


def get_etf_flow(symbol, related_claim):
    """取得 BTC 或 ETH 現貨 ETF 的資金流向摘要。

    呼叫 SosoValue API 取得最新 ETF 淨流入/流出資料，
    包含每日淨流入、累積淨流入、總淨資產、各基金明細。

    Args:
        symbol: 幣種代碼（僅支援 BTC 或 ETH）
        related_claim: Agent 說明取數目的

    Returns:
        Contract C1 dict or error dict
    """
    source_url = f"{_BASE_URL}/etfs"
    start_time = time.time()

    try:
        symbol_upper = symbol.upper().strip()

        # 驗證幣種
        if symbol_upper not in _SUPPORTED_SYMBOLS:
            return {
                "error": f"[get_etf_flow] ETF 資金流僅支援 BTC 與 ETH，不支援 {symbol_upper}。"
                         f"（目前美國市場僅有 BTC/ETH 現貨 ETF）",
                "source": source_url,
                "content_reference": {},
            }

        # 檢查 API 金鑰
        api_key = config.SOSOVALUE_API_KEY
        if not api_key:
            elapsed_ms = int((time.time() - start_time) * 1000)
            evidence.log_execution_step(
                "get_etf_flow", "error", elapsed_ms,
                note="SOSOVALUE_API_KEY not configured"
            )
            return {
                "error": "[get_etf_flow] SOSOVALUE_API_KEY 未設定，無法查詢 ETF 資金流",
                "source": source_url,
                "content_reference": {},
            }

        # 組裝 headers
        headers = {
            **_HEADERS_BASE,
            "x-soso-api-key": api_key,
        }

        # 呼叫 ETF 摘要 endpoint
        params = {"symbol": symbol_upper}
        resp = requests.get(
            f"{_BASE_URL}/etfs",
            headers=headers,
            params=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        # SosoValue API 回傳格式：{"code": 0, "data": {...}, ...}
        # 若 code != 0 表示 API 層錯誤
        if isinstance(data, dict) and data.get("code") and data.get("code") != 0:
            error_msg = data.get("msg") or data.get("message") or f"API error code {data.get('code')}"
            raise RuntimeError(f"SosoValue API error: {error_msg}")

        # 解析資料
        etf_data = data.get("data", data) if isinstance(data, dict) else data
        result = _parse_etf_response(etf_data, symbol_upper)

        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # 組裝 content_reference
        content_reference = {
            "api_endpoint": f"{_BASE_URL}/etfs",
            "query_params": params,
            "symbol": symbol_upper,
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
            "human_url": f"https://sosovalue.com/assets/etf/us-{symbol_upper.lower()}-spot",
        }
        content_reference.update(result.get("metrics", {}))

        # 組裝 summary
        metrics = result.get("metrics", {})
        summary = _build_summary(symbol_upper, metrics)

        # 記錄成功
        evidence.log_execution_step(
            "get_etf_flow", "success", elapsed_ms,
            note=summary[:100]
        )

        return {
            "raw": etf_data,
            "source": source_url,
            "content_reference": content_reference,
            "summary": summary,
        }

    except requests.exceptions.HTTPError as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        status_code = e.response.status_code if e.response is not None else "unknown"

        # 特殊處理 429 rate limit
        if status_code == 429:
            note = "SosoValue API rate limit exceeded"
        else:
            note = f"HTTP {status_code}: {str(e)}"

        evidence.log_execution_step("get_etf_flow", "error", elapsed_ms, note=note)
        return {
            "error": f"[get_etf_flow] {note}",
            "source": source_url,
            "content_reference": {},
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            "get_etf_flow", "error", elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}"
        )
        return {
            "error": f"[get_etf_flow] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def _parse_etf_response(data, symbol):
    """解析 SosoValue ETF API 回傳資料，提取關鍵指標。

    適應多種回傳格式（list of funds / summary object）。
    """
    metrics = {}

    if isinstance(data, dict):
        # 摘要格式：直接取欄位
        metrics["daily_net_inflow_usd"] = _safe_float(
            data.get("dailyNetInflow") or data.get("daily_net_inflow") or
            data.get("totalNetInflow") or data.get("netInflow")
        )
        metrics["cumulative_net_inflow_usd"] = _safe_float(
            data.get("cumulativeNetInflow") or data.get("cumulative_net_inflow") or
            data.get("totalCumulativeNetInflow")
        )
        metrics["total_net_assets_usd"] = _safe_float(
            data.get("totalNetAssets") or data.get("total_net_assets") or
            data.get("netAssets")
        )
        metrics["total_value_traded_usd"] = _safe_float(
            data.get("totalValueTraded") or data.get("total_value_traded") or
            data.get("volume")
        )
        metrics["as_of_date"] = (
            data.get("asOfDate") or data.get("date") or
            data.get("dataDate") or ""
        )

        # 個別基金明細（如果有）
        funds = data.get("funds") or data.get("list") or data.get("etfList") or []
        if isinstance(funds, list) and funds:
            metrics["top_funds"] = _parse_fund_list(funds)

    elif isinstance(data, list):
        # 列表格式：可能是各基金的陣列
        metrics["top_funds"] = _parse_fund_list(data)
        # 計算彙總
        total_inflow = sum(_safe_float(f.get("netInflow") or f.get("dailyNetInflow") or 0) for f in data)
        total_assets = sum(_safe_float(f.get("netAssets") or f.get("totalNetAssets") or 0) for f in data)
        metrics["daily_net_inflow_usd"] = total_inflow
        metrics["total_net_assets_usd"] = total_assets

    # 清理 None 值
    metrics = {k: v for k, v in metrics.items() if v is not None and v != ""}

    return {"metrics": metrics}


def _parse_fund_list(funds):
    """解析個別基金列表，取 top 5。"""
    parsed = []
    for fund in funds[:10]:
        if not isinstance(fund, dict):
            continue
        parsed.append({
            "ticker": fund.get("ticker") or fund.get("symbol") or fund.get("name", ""),
            "sponsor": fund.get("sponsor") or fund.get("issuer") or "",
            "net_inflow": _safe_float(fund.get("netInflow") or fund.get("dailyNetInflow")),
            "net_assets": _safe_float(fund.get("netAssets") or fund.get("totalNetAssets")),
        })
    # 依淨流入排序
    parsed.sort(key=lambda x: abs(x.get("net_inflow") or 0), reverse=True)
    return parsed[:5]


def _build_summary(symbol, metrics):
    """組裝給模型看的精簡摘要。"""
    parts = [f"US {symbol} Spot ETF 資金流向（來源：SosoValue）："]

    daily = metrics.get("daily_net_inflow_usd")
    if daily is not None:
        direction = "淨流入" if daily >= 0 else "淨流出"
        parts.append(f"每日{direction} ${abs(daily)/1_000_000:.1f}M")

    cumulative = metrics.get("cumulative_net_inflow_usd")
    if cumulative is not None:
        parts.append(f"累積淨流入 ${cumulative/1_000_000_000:.2f}B")

    assets = metrics.get("total_net_assets_usd")
    if assets is not None:
        parts.append(f"總淨資產 ${assets/1_000_000_000:.2f}B")

    volume = metrics.get("total_value_traded_usd")
    if volume is not None:
        parts.append(f"日交易量 ${volume/1_000_000:.0f}M")

    as_of = metrics.get("as_of_date")
    if as_of:
        parts.append(f"資料日期 {as_of}")

    # Top funds
    top_funds = metrics.get("top_funds", [])
    if top_funds:
        fund_lines = []
        for f in top_funds[:3]:
            ticker = f.get("ticker", "?")
            inflow = f.get("net_inflow")
            if inflow is not None:
                sign = "+" if inflow >= 0 else ""
                fund_lines.append(f"{ticker} {sign}${inflow/1_000_000:.1f}M")
        if fund_lines:
            parts.append(f"Top 基金: {', '.join(fund_lines)}")

    return "；".join(parts)


def _safe_float(value):
    """安全轉換為 float，失敗回傳 None。"""
    if value is None:
        return None
    try:
        result = float(value)
        return result if result == result else None  # NaN check
    except (ValueError, TypeError):
        return None
