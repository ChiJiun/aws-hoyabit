"""
sentiment.py — 市場情緒工具

資料來源：alternative.me Fear & Greed Index
免費、不需註冊、不需 API 金鑰，是這次專案取得情緒資料最穩定的途徑。
（Reddit API 自 2025 年 11 月起即使非商業用途也需申請核准、審核 2-4 週，
  時程上不適合這次比賽，故不採用。）
"""

import time
from datetime import datetime, timezone

import requests

import config
import evidence
from tools.quality import make_anomaly_flag

_API_BASE = "https://api.alternative.me/fng/"
_TIMEOUT = 30


def get_sentiment(related_claim, lookback_days=30):
    """取得市場恐懼與貪婪指數的當前值與近期走勢。

    這是全市場的單一指數（0-100，從極度恐慌到極度貪婪），
    五個幣種都參考同一個數值，不需要依幣種分派。

    Args:
        related_claim: Agent 框架所需參數，說明取數目的
        lookback_days: 回溯天數，預設 30 天

    Returns:
        統一格式 dict：成功時含 raw/source/content_reference/summary，
        失敗時含 error/source/content_reference。
    """
    source_url = f"{_API_BASE}?limit={lookback_days}&format=json"
    start_time = time.time()

    try:
        resp = requests.get(source_url, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        entries = data.get("data", [])
        if not entries:
            raise ValueError("API 回應中缺少 data 陣列或為空")

        # 最新一筆（data 陣列是 most-recent-first）
        current = entries[0]
        current_value = int(current.get("value", 0))
        current_classification = current.get("value_classification", "Unknown")
        current_timestamp = int(current.get("timestamp", 0))
        current_date = datetime.fromtimestamp(
            current_timestamp, tz=timezone.utc
        ).strftime("%Y-%m-%d")

        # 計算近期走勢：取最舊一筆作比較
        oldest = entries[-1]
        oldest_value = int(oldest.get("value", 0))
        oldest_timestamp = int(oldest.get("timestamp", 0))
        oldest_date = datetime.fromtimestamp(
            oldest_timestamp, tz=timezone.utc
        ).strftime("%Y-%m-%d")

        value_change = current_value - oldest_value

        # 走勢描述
        if value_change > 10:
            trend_desc = "明顯偏向貪婪"
        elif value_change > 0:
            trend_desc = "略偏貪婪"
        elif value_change < -10:
            trend_desc = "明顯偏向恐慌"
        elif value_change < 0:
            trend_desc = "略偏恐慌"
        else:
            trend_desc = "持平"

        # 組裝 raw：保留原始 API 回應
        raw_data = data

        # 組裝 content_reference
        content_reference = {
            "api_endpoint": source_url,
            "human_url": "https://alternative.me/crypto/fear-and-greed-index/",
            "query_time_range": f"{oldest_date} ~ {current_date} ({lookback_days} 天)",
            "current_index": current_value,
            "current_classification": current_classification,
            "oldest_index": oldest_value,
            "value_change": value_change,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # 組裝 summary
        summary = (
            f"加密市場恐懼與貪婪指數（Fear & Greed Index）："
            f"當前 {current_value}（{current_classification}）；"
            f"近 {lookback_days} 天走勢{trend_desc}"
            f"（從 {oldest_value} 變至 {current_value}，變化 {value_change:+d}）。"
            f"注意：此為全市場指標，非個別幣種專屬情緒。"
        )

        # 記錄成功執行
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="get_sentiment",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"FnG index={current_value} ({current_classification}), "
                 f"trend={value_change:+d} over {lookback_days}d",
        )

        # --- A6 異常偵測：F&G 極端值 + 7日急變 ---
        anomaly_flags = []
        thresholds = getattr(config, "ANOMALY_THRESHOLDS", {})
        fg_low = thresholds.get("fg_extreme_low", 20)
        fg_high = thresholds.get("fg_extreme_high", 80)
        fg_rapid_change = thresholds.get("fg_rapid_change_7d", 30)

        if current_value <= fg_low:
            anomaly_flags.append(make_anomaly_flag(
                signal_id="A6_extreme_fear",
                name="情緒極端恐慌",
                severity="significant" if current_value <= 10 else "notable",
                direction="bearish",
                value=current_value,
                unit="index",
                threshold=f"≤ {fg_low}",
                window=f"{lookback_days}d lookback",
                as_of=current_date,
                message=f"Fear & Greed Index {current_value}（{current_classification}），處於極端恐慌區間",
            ))
        elif current_value >= fg_high:
            anomaly_flags.append(make_anomaly_flag(
                signal_id="A6_extreme_greed",
                name="情緒極端貪婪",
                severity="significant" if current_value >= 90 else "notable",
                direction="bullish",
                value=current_value,
                unit="index",
                threshold=f"≥ {fg_high}",
                window=f"{lookback_days}d lookback",
                as_of=current_date,
                message=f"Fear & Greed Index {current_value}（{current_classification}），處於極端貪婪區間",
            ))

        # 7日急變檢查（需要至少 7 筆資料）
        if len(entries) >= 7:
            seven_day_ago_value = int(entries[6].get("value", 0))
            change_7d = current_value - seven_day_ago_value
            if abs(change_7d) >= fg_rapid_change:
                direction = "bullish" if change_7d > 0 else "bearish"
                anomaly_flags.append(make_anomaly_flag(
                    signal_id="A6_rapid_shift",
                    name="情緒 7 日急變",
                    severity="notable",
                    direction=direction,
                    value=change_7d,
                    unit="points/7d",
                    threshold=f"|Δ7d| ≥ {fg_rapid_change}",
                    window="7d",
                    as_of=current_date,
                    message=f"Fear & Greed 7 日變化 {change_7d:+d} 點（{seven_day_ago_value} → {current_value}），情緒快速轉向",
                ))

        result = {
            "raw": raw_data,
            "source": source_url,
            "content_reference": content_reference,
            "summary": summary,
        }
        if anomaly_flags:
            result["anomaly_flags"] = anomaly_flags
        return result

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="get_sentiment",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[get_sentiment] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }
