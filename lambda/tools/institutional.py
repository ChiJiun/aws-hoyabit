"""
institutional.py — 機構與監管資料工具

資料來源：CFTC COT 報告、SEC EDGAR、Coin Metrics Community
全部免費、免鑰

設計考量：
- CFTC COT：每週更新（週二資料週五釋出），顯示 CME BTC 期貨的機構持倉方向
  投機淨多頭極端 = smart money 擁擠方向，歷史上極端值常見反轉
- SEC EDGAR：加密相關監管文件的一手來源，ETF 申請/批准、執法行動直接影響市場
- Coin Metrics Community：機構級鏈上/市場指標（MVRV、NVT、活躍地址），
  MVRV > 3 = 歷史性高估區、NVT 極高 = 交易活動不支撐估值
- 所有 HTTP 呼叫設 timeout，失敗回傳 error dict，絕不拋出未處理例外
"""

import time
import json
from datetime import datetime, timedelta, timezone

import requests

import evidence

# ---- HTTP 請求統一配置 ----
_TIMEOUT = 30
_HEADERS = {"User-Agent": "HoyabitAgent team@example.com"}

# ---- CFTC JSON API 設定 ----
_CFTC_JSON_API = (
    "https://publicreporting.cftc.gov/resource/jun7-fc8e.json"
    "?$where=market_and_exchange_names like '%25BITCOIN%25'"
    "&$limit=10&$order=report_date_as_yyyy_mm_dd DESC"
)

# ---- SEC EDGAR 設定 ----
_SEC_EDGAR_BASE = "https://efts.sec.gov/LATEST/search-index"

# ---- Coin Metrics Community API 設定 ----
_COINMETRICS_BASE = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"

# ---- Coin Metrics 幣種映射 ----
_SYMBOL_TO_ASSET = {
    "BTC": "btc",
    "ETH": "eth",
    "SOL": "sol",
    "BNB": "bnb",
    "XRP": "xrp",
}


def get_cftc_cot(symbol, related_claim):
    """取得 CFTC Commitments of Traders 報告中 CME Bitcoin 期貨的機構持倉數據。

    使用 CFTC JSON API（比下載 10MB 大檔更高效），取最近 10 筆報告。
    計算投機淨部位 = Non-Commercial Long - Non-Commercial Short。

    Args:
        symbol: 目前僅支援 BTC
        related_claim: 這筆資料要用來檢驗什麼判斷

    Returns:
        Contract C1 dict or error dict
    """
    source_url = _CFTC_JSON_API
    start_time = time.time()

    try:
        symbol_upper = symbol.upper().strip()
        if symbol_upper != "BTC":
            return {
                "error": f"[get_cftc_cot] CFTC COT 僅支援 BTC（CME Bitcoin Futures），不支援 {symbol_upper}"
            }

        # 呼叫 CFTC JSON API
        resp = requests.get(_CFTC_JSON_API, headers=_HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if not data or not isinstance(data, list):
            return {
                "error": "[get_cftc_cot] CFTC API 回傳空資料或格式異常",
                "source": source_url,
                "content_reference": {},
            }

        # 解析最近一筆報告
        latest = data[0]
        report_date = latest.get("report_date_as_yyyy_mm_dd", "unknown")

        # 取得各持倉欄位（CFTC JSON API 欄位名稱）
        noncomm_long = _safe_int(latest.get("noncomm_positions_long_all", 0))
        noncomm_short = _safe_int(latest.get("noncomm_positions_short_all", 0))
        comm_long = _safe_int(latest.get("comm_positions_long_all", 0))
        comm_short = _safe_int(latest.get("comm_positions_short_all", 0))

        # 計算淨部位
        net_speculative = noncomm_long - noncomm_short
        net_commercial = comm_long - comm_short

        # 組裝歷史淨投機部位（用於趨勢觀察）
        historical_net = []
        for row in data:
            row_date = row.get("report_date_as_yyyy_mm_dd", "")
            row_noncomm_long = _safe_int(row.get("noncomm_positions_long_all", 0))
            row_noncomm_short = _safe_int(row.get("noncomm_positions_short_all", 0))
            historical_net.append({
                "date": row_date,
                "net_speculative": row_noncomm_long - row_noncomm_short,
            })

        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # 組裝 summary
        spec_direction = "淨多頭" if net_speculative > 0 else "淨空頭"
        comm_direction = "淨多頭" if net_commercial > 0 else "淨空頭"
        summary = (
            f"CFTC COT (BTC Futures): 投機{spec_direction} {abs(net_speculative)} 合約, "
            f"商業{comm_direction} {abs(net_commercial)} 合約, "
            f"報告日 {report_date}"
        )

        # 組裝 content_reference
        content_reference = {
            "endpoint": _CFTC_JSON_API,
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
            "report_date": report_date,
            "noncommercial_long": noncomm_long,
            "noncommercial_short": noncomm_short,
            "commercial_long": comm_long,
            "commercial_short": comm_short,
            "net_speculative": net_speculative,
            "net_commercial": net_commercial,
        }

        # 組裝 raw
        raw_data = {
            "latest_report": latest,
            "historical_net_speculative": historical_net,
            "records_count": len(data),
        }

        evidence.log_execution_step(
            "get_cftc_cot", "success", elapsed_ms, note=summary[:100]
        )

        return {
            "raw": raw_data,
            "source": source_url,
            "content_reference": content_reference,
            "summary": summary,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            "get_cftc_cot", "error", elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}"
        )
        return {
            "error": f"[get_cftc_cot] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def get_sec_filings(keywords, related_claim):
    """搜尋 SEC EDGAR 近期加密相關監管文件。

    使用 EDGAR full-text search API 搜尋近 30 天內含有指定關鍵字的文件。
    SEC 要求 User-Agent 含公司名與 email。

    Args:
        keywords: 搜尋關鍵字（如 bitcoin, ethereum, crypto ETF）
        related_claim: 這筆資料要用來檢驗什麼判斷

    Returns:
        Contract C1 dict or error dict
    """
    source_url = _SEC_EDGAR_BASE
    start_time = time.time()

    try:
        # 計算日期範圍（近 30 天）
        today = datetime.now(timezone.utc).date()
        start_date = today - timedelta(days=30)

        # 組裝搜尋參數
        params = {
            "q": keywords,
            "dateRange": "custom",
            "startdt": start_date.isoformat(),
            "enddt": today.isoformat(),
        }

        resp = requests.get(
            _SEC_EDGAR_BASE, params=params, headers=_HEADERS, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()

        # EDGAR search API 回傳格式：{"hits": {"hits": [...], "total": {...}}}
        hits_wrapper = data.get("hits", {})
        total_info = hits_wrapper.get("total", {})
        total_count = total_info.get("value", 0) if isinstance(total_info, dict) else 0
        hits = hits_wrapper.get("hits", [])

        # 解析搜尋結果
        filings = []
        for hit in hits[:10]:  # 取前 10 筆
            source_data = hit.get("_source", {})
            filing = {
                "title": source_data.get("display_names", [""]),
                "form_type": source_data.get("form_type", ""),
                "file_date": source_data.get("file_date", ""),
                "entity_name": source_data.get("entity_name", ""),
            }
            # display_names 可能是 list
            if isinstance(filing["title"], list):
                filing["title"] = filing["title"][0] if filing["title"] else ""
            filings.append(filing)

        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # 組裝 summary
        latest_title = filings[0]["title"] if filings else "無"
        latest_date = filings[0]["file_date"] if filings else "N/A"
        summary = (
            f"SEC EDGAR: 近30天 {total_count} 篇加密相關監管文件 "
            f"(搜尋: {keywords}), 最新: {latest_title[:50]} ({latest_date})"
        )

        # 組裝 content_reference
        content_reference = {
            "endpoint": _SEC_EDGAR_BASE,
            "query_params": params,
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
            "total_filings": total_count,
            "top_filings": filings[:5],
        }

        # 組裝 raw
        raw_data = {
            "total_count": total_count,
            "filings": filings,
            "query": keywords,
            "date_range": {
                "start": start_date.isoformat(),
                "end": today.isoformat(),
            },
        }

        evidence.log_execution_step(
            "get_sec_filings", "success", elapsed_ms, note=summary[:100]
        )

        return {
            "raw": raw_data,
            "source": source_url,
            "content_reference": content_reference,
            "summary": summary,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            "get_sec_filings", "error", elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}"
        )
        return {
            "error": f"[get_sec_filings] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def get_coin_metrics(symbol, metrics, related_claim):
    """取得 Coin Metrics Community 的機構級鏈上/市場指標。

    免費、免鑰的 Community API，提供 MVRV、NVT、活躍地址等機構級指標。
    取最近 30 天日頻資料。

    Args:
        symbol: 幣種代號（BTC/ETH/SOL/BNB/XRP）
        metrics: 指標列表，可選：RealizedCap, CapMVRVCur, NVTAdj, AdrActCnt, TxCnt, FeeMeanUSD
        related_claim: 這筆資料要用來檢驗什麼判斷

    Returns:
        Contract C1 dict or error dict
    """
    source_url = _COINMETRICS_BASE
    start_time = time.time()

    try:
        symbol_upper = symbol.upper().strip()
        if symbol_upper not in _SYMBOL_TO_ASSET:
            return {
                "error": f"[get_coin_metrics] 不支援的幣種: {symbol_upper}，"
                         f"支援: {list(_SYMBOL_TO_ASSET.keys())}"
            }

        asset = _SYMBOL_TO_ASSET[symbol_upper]
        metrics_csv = ",".join(metrics)

        # 組裝 API 請求
        params = {
            "assets": asset,
            "metrics": metrics_csv,
            "frequency": "1d",
            "limit": 30,
        }

        resp = requests.get(
            _COINMETRICS_BASE, params=params, headers=_HEADERS, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()

        # Coin Metrics 回傳格式：{"data": [{...}, ...]}
        series = data.get("data", [])
        if not series:
            return {
                "error": f"[get_coin_metrics] {symbol_upper} 的 {metrics_csv} 回傳空資料",
                "source": source_url,
                "content_reference": {},
            }

        # 取最新一筆
        latest = series[-1]
        latest_time = latest.get("time", "unknown")

        # 解析各指標的最新值與趨勢
        metric_values = {}
        for m in metrics:
            values = [float(row[m]) for row in series if row.get(m) is not None]
            if values:
                metric_values[m] = {
                    "latest": values[-1],
                    "min_30d": min(values),
                    "max_30d": max(values),
                    "avg_30d": sum(values) / len(values),
                    "data_points": len(values),
                }

        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # 組裝 summary
        summary_parts = [f"Coin Metrics {symbol_upper}:"]
        for m, vals in metric_values.items():
            latest_val = vals["latest"]
            # 格式化：大數用 k/M/B 表示
            if m == "AdrActCnt":
                summary_parts.append(f"Active Addresses {latest_val/1000:.1f}k")
            elif m == "TxCnt":
                summary_parts.append(f"Tx Count {latest_val/1000:.1f}k")
            elif m == "RealizedCap":
                summary_parts.append(f"Realized Cap ${latest_val/1e9:.2f}B")
            elif m == "CapMVRVCur":
                summary_parts.append(f"MVRV {latest_val:.2f}")
            elif m == "NVTAdj":
                summary_parts.append(f"NVT {latest_val:.1f}")
            elif m == "FeeMeanUSD":
                summary_parts.append(f"Avg Fee ${latest_val:.2f}")
            else:
                summary_parts.append(f"{m} {latest_val:.4g}")

        summary = " ".join(summary_parts)

        # 組裝 content_reference
        content_reference = {
            "endpoint": _COINMETRICS_BASE,
            "query_params": params,
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
            "latest_time": latest_time,
            "metric_values": metric_values,
        }

        # 組裝 raw
        raw_data = {
            "series": series,
            "metric_values": metric_values,
            "asset": asset,
            "metrics_requested": metrics,
            "data_points": len(series),
        }

        evidence.log_execution_step(
            "get_coin_metrics", "success", elapsed_ms, note=summary[:100]
        )

        return {
            "raw": raw_data,
            "source": source_url,
            "content_reference": content_reference,
            "summary": summary,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            "get_coin_metrics", "error", elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}"
        )
        return {
            "error": f"[get_coin_metrics] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


# ---- 工具函式 ----

def _safe_int(value):
    """安全將值轉為 int，失敗回傳 0。"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0
