"""
macro.py — 總體經濟工具

資料來源：FRED（美國聖路易聯準銀行經濟資料庫）

設計考量：
- FRED 提供免費的總體經濟指標 API，涵蓋 DXY、公債殖利率、聯邦基金利率等
- 排定事件（FOMC、CPI）使用硬編碼日曆——這些日期由 Fed/BLS 預先公布，
  不需要付費即時日曆 API，且對短期方向判斷極有價值
- 所有外部 API 呼叫設 timeout，失敗回傳 error dict，絕不拋出未處理例外
"""

from datetime import datetime, timedelta, timezone

import requests

import config
from tools.quality import make_anomaly_flag


# ---- 指標名稱 → FRED Series ID 映射 ----
INDICATOR_MAP = {
    "dxy": {
        "series_id": "DTWEXBGS",
        "name": "Trade Weighted U.S. Dollar Index: Broad, Goods and Services",
        "short_name": "美元指數(DXY)",
    },
    "treasury_10y": {
        "series_id": "DGS10",
        "name": "10-Year Treasury Constant Maturity Rate",
        "short_name": "10年期公債殖利率",
    },
    "fed_funds_rate": {
        "series_id": "DFF",
        "name": "Federal Funds Effective Rate",
        "short_name": "聯邦基金利率",
    },
}

# ---- 2025–2026 排定事件日曆（公開資訊，預先排定） ----
# FOMC 會議日期來源：Federal Reserve 公布的會議排程
# CPI 公布日期來源：Bureau of Labor Statistics 公布排程
SCHEDULED_EVENTS = [
    # 2025 FOMC 會議（結束日）
    {"date": "2025-01-29", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2025-03-19", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2025-05-07", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2025-06-18", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2025-07-30", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2025-09-17", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2025-10-29", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2025-12-17", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    # 2026 FOMC 會議（結束日）
    {"date": "2026-01-28", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2026-03-18", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2026-04-29", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2026-06-17", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2026-07-29", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2026-09-16", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2026-10-28", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    {"date": "2026-12-16", "event_name": "FOMC Meeting", "description": "Federal Open Market Committee 利率決議"},
    # 2025 CPI 公布日
    {"date": "2025-01-15", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-02-12", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-03-12", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-04-10", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-05-13", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-06-11", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-07-11", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-08-12", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-09-10", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-10-14", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-11-12", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2025-12-10", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    # 2026 CPI 公布日
    {"date": "2026-01-14", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-02-11", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-03-11", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-04-10", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-05-12", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-06-10", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-07-14", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-08-12", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-09-15", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-10-13", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-11-12", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
    {"date": "2026-12-10", "event_name": "CPI Release", "description": "Consumer Price Index 月度數據公布"},
]

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_upcoming_events():
    # 功能：取得未來 30 天內已排定的重要總經事件（FOMC 會議、CPI 公布日）。
    # 為什麼重要：「已排定的事件」是判斷短期方向性最有力的證據之一。
    #            例如三天後有 FOMC 會議，就足以推翻「短期缺乏明確方向」的假設。
    #            這類資料在日曆上、不在價格數據裡，容易被忽略。
    # 回傳：事件清單 list[dict]，每項含 date（ISO 8601）、event_name、description

    today = datetime.now(timezone.utc).date()
    window_end = today + timedelta(days=30)

    upcoming = []
    for event in SCHEDULED_EVENTS:
        event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        if today <= event_date <= window_end:
            upcoming.append({
                "date": event["date"],
                "event_name": event["event_name"],
                "description": event["description"],
            })

    # 依日期排序
    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def get_macro(indicators, related_claim, lookback_days=90):
    # 功能：取得總體經濟指標的近期走勢。
    # 步驟：
    #   1. 檢查 FRED_API_KEY 是否存在
    #   2. 將 indicators 名稱映射到 FRED series ID
    #   3. 逐一呼叫 FRED API 取得觀測值
    #   4. 整合 fetch_upcoming_events 結果
    #   5. 組裝 content_reference 與 summary
    # 回傳：統一格式 dict（raw、source、content_reference、summary）

    try:
        # 步驟 1：檢查 API 金鑰
        if not config.FRED_API_KEY:
            return {
                "error": "[get_macro] FRED_API_KEY 未設定，無法取得總經資料",
                "source": FRED_BASE_URL,
                "content_reference": {},
            }

        # 步驟 2：計算查詢時間範圍
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        # 步驟 3：逐一取得指標資料
        results = {}
        series_ids_queried = []

        indicator_aliases = {
            "us10y": "treasury_10y",
            "dgs10": "treasury_10y",
            "fedfunds": "fed_funds_rate",
            "dff": "fed_funds_rate",
        }
        for indicator in indicators:
            requested_key = indicator.lower().strip()
            indicator_key = indicator_aliases.get(requested_key, requested_key)

            if indicator_key not in INDICATOR_MAP:
                results[indicator_key] = {
                    "error": f"不支援的指標: {indicator}，支援: {list(INDICATOR_MAP.keys())}",
                }
                continue

            meta = INDICATOR_MAP[indicator_key]
            series_id = meta["series_id"]
            series_ids_queried.append(series_id)

            # 呼叫 FRED API
            params = {
                "series_id": series_id,
                "api_key": config.FRED_API_KEY,
                "file_type": "json",
                "observation_start": start_date,
                "observation_end": end_date,
            }

            try:
                resp = requests.get(FRED_BASE_URL, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as api_err:
                results[indicator_key] = {
                    "error": f"FRED API 呼叫失敗 ({series_id}): {type(api_err).__name__}: {str(api_err)}",
                }
                continue

            # 解析觀測值（過濾掉 "." 缺值）
            observations = data.get("observations", [])
            valid_obs = []
            for obs in observations:
                if obs.get("value") and obs["value"] != ".":
                    try:
                        valid_obs.append({
                            "date": obs["date"],
                            "value": float(obs["value"]),
                        })
                    except (ValueError, TypeError):
                        continue

            if not valid_obs:
                results[indicator_key] = {
                    "series_id": series_id,
                    "name": meta["name"],
                    "observations": [],
                    "note": "查詢期間內無有效觀測值",
                }
                continue

            # 計算摘要統計
            values = [o["value"] for o in valid_obs]
            latest_value = valid_obs[-1]["value"]
            latest_date = valid_obs[-1]["date"]
            first_value = valid_obs[0]["value"]
            change = latest_value - first_value
            change_pct = (change / first_value * 100) if first_value != 0 else 0
            high_value = max(values)
            low_value = min(values)

            results[indicator_key] = {
                "series_id": series_id,
                "name": meta["name"],
                "short_name": meta["short_name"],
                "latest_value": latest_value,
                "latest_date": latest_date,
                "first_value": first_value,
                "change": round(change, 4),
                "change_pct": round(change_pct, 2),
                "high": high_value,
                "low": low_value,
                "observation_count": len(valid_obs),
                "observations": valid_obs,
            }

        # 步驟 4：取得排定事件
        upcoming_events = fetch_upcoming_events()

        # 步驟 5：組裝 content_reference
        content_reference = {
            "fred_series_ids": series_ids_queried,
            "human_urls": [
                {
                    "label": INDICATOR_MAP[key]["short_name"],
                    "url": f"https://fred.stlouisfed.org/series/{INDICATOR_MAP[key]['series_id']}",
                }
                for key in results if key in INDICATOR_MAP and "error" not in results[key]
            ],
            "query_range": f"{start_date} ~ {end_date}",
            "lookback_days": lookback_days,
            "indicators_summary": {},
            "upcoming_events_count": len(upcoming_events),
        }

        for key, res in results.items():
            if "error" not in res and "latest_value" in res:
                content_reference["indicators_summary"][key] = {
                    "series_id": res["series_id"],
                    "latest_value": res["latest_value"],
                    "latest_date": res["latest_date"],
                    "change_pct": res["change_pct"],
                }

        # 步驟 6：組裝 summary（控制在 ~500 tokens 內）
        summary_parts = []
        for key, res in results.items():
            if "error" in res:
                summary_parts.append(f"- {key}: 取得失敗 ({res['error']})")
            elif "latest_value" in res:
                direction = "↑" if res["change"] > 0 else "↓" if res["change"] < 0 else "→"
                summary_parts.append(
                    f"- {res['short_name']}({res['series_id']}): "
                    f"最新 {res['latest_value']:.4f} ({res['latest_date']}), "
                    f"{lookback_days}日變化 {direction}{abs(res['change_pct']):.2f}%, "
                    f"區間 [{res['low']:.4f}, {res['high']:.4f}]"
                )
            else:
                summary_parts.append(f"- {key}: 無有效資料")

        # 排定事件摘要
        if upcoming_events:
            event_lines = []
            for ev in upcoming_events[:5]:  # 最多列出 5 筆
                event_lines.append(f"  {ev['date']} {ev['event_name']}")
            summary_parts.append(f"- 未來30天排定事件 ({len(upcoming_events)}筆):")
            summary_parts.extend(event_lines)
        else:
            summary_parts.append("- 未來30天無排定的重大總經事件")

        summary = f"總經指標 ({start_date}~{end_date}):\n" + "\n".join(summary_parts)

        # 組裝原始資料（不含完整 observations 以控制大小，僅保留統計）
        raw_data = {
            "indicators": {},
            "upcoming_events": upcoming_events,
            "query_params": {
                "indicators_requested": indicators,
                "lookback_days": lookback_days,
                "start_date": start_date,
                "end_date": end_date,
            },
        }
        for key, res in results.items():
            raw_data["indicators"][key] = res

        source_url = f"{FRED_BASE_URL}?series_id={','.join(series_ids_queried)}&observation_start={start_date}&observation_end={end_date}"

        # --- A10 異常偵測：DXY / 10Y 殖利率 20 日變化幅度近一年百分位 ≥ 85 ---
        anomaly_flags = []
        thresholds = getattr(config, "ANOMALY_THRESHOLDS", {})
        macro_pct_high = thresholds.get("macro_change_percentile_high", 85.0)

        for key in ("dxy", "treasury_10y"):
            res = results.get(key)
            if not res or "observations" not in res:
                continue
            obs_values = [o["value"] for o in res.get("observations", [])]
            if len(obs_values) < 25:
                continue  # 需要至少 20+5 個觀測值才能計算滾動變化

            # 計算所有滾動 20 期絕對變化
            rolling_changes = []
            for i in range(20, len(obs_values)):
                change = abs(obs_values[i] - obs_values[i - 20])
                rolling_changes.append(change)

            if not rolling_changes:
                continue

            # 最新的 20 期變化
            current_change = abs(obs_values[-1] - obs_values[-21]) if len(obs_values) >= 21 else None
            if current_change is None:
                continue

            # 計算百分位
            below_count = sum(1 for c in rolling_changes if c <= current_change)
            percentile = (below_count / len(rolling_changes)) * 100

            if percentile >= macro_pct_high:
                short_name = res.get("short_name", key)
                direction_val = obs_values[-1] - obs_values[-21]
                direction = "tightening" if direction_val > 0 else "easing"
                anomaly_flags.append(make_anomaly_flag(
                    signal_id=f"A10_macro_regime_shift_{key}",
                    name=f"總經環境轉向（{short_name}）",
                    severity="significant" if percentile >= 95 else "notable",
                    direction=direction,
                    value=round(direction_val, 4),
                    unit="20d absolute change",
                    percentile=round(percentile, 1),
                    threshold=f"百分位 ≥ {macro_pct_high}",
                    window="20d change vs rolling history",
                    as_of=res.get("latest_date", ""),
                    message=f"{short_name} 20 日變化 {direction_val:+.4f}，"
                            f"幅度為近一年第 {percentile:.0f} 百分位（門檻 {macro_pct_high}），"
                            f"方向：{'緊縮' if direction == 'tightening' else '寬鬆'}",
                ))

        result = {
            "raw": raw_data,
            "source": source_url if series_ids_queried else FRED_BASE_URL,
            "content_reference": content_reference,
            "summary": summary,
        }
        if anomaly_flags:
            result["anomaly_flags"] = anomaly_flags
        return result

    except Exception as e:
        return {
            "error": f"[get_macro] {type(e).__name__}: {str(e)}",
            "source": FRED_BASE_URL,
            "content_reference": {},
        }
