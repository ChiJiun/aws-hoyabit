"""
quant.py — 技術指標計算工具

這個工具不呼叫任何外部 API，純粹是本地計算。
存在的理由：所有數字必須由程式決定性地算出來，不能讓模型心算。
模型心算數字是現場 Demo 時最容易被評審驗證出錯的地方。
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone


def calc_atr_pct(df, window):
    """計算 ATR（平均真實區間）佔價格的百分比序列。

    True Range = max(H-L, |H-prevC|, |L-prevC|)
    ATR = rolling mean(TR, window)
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)

    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(window=window).mean()
    result = atr / close.replace(0, np.nan) * 100
    return result.replace([np.inf, -np.inf], np.nan)


def calc_bollinger_bandwidth(df, window):
    """計算布林帶寬比率序列（上下軌距離除以中軌）。"""
    close = df["close"].astype(float)
    mid = close.rolling(window=window).mean()
    std = close.rolling(window=window).std()
    bandwidth = (4 * std) / mid.replace(0, np.nan)
    return bandwidth.replace([np.inf, -np.inf], np.nan)


def calc_adx(df, window):
    """計算 ADX（平均趨向指標）。

    標準 +DM/-DM/TR/+DI/-DI/DX/ADX 計算流程。
    回傳最後一筆 ADX 值。
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # +DM / -DM
    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    # True Range
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Smoothed with EWM (span=window)
    atr = true_range.ewm(span=window, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(span=window, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(span=window, adjust=False).mean()

    # +DI / -DI
    plus_di = (plus_dm_smooth / atr) * 100
    minus_di = (minus_dm_smooth / atr) * 100

    # DX
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = (di_diff / di_sum.replace(0, np.nan)) * 100

    # ADX = EWM of DX
    adx = dx.ewm(span=window, adjust=False).mean()

    # 常數價格或 DI 分母全為零代表沒有可辨識趨勢，ADX 定義為 0。
    return adx.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def calc_percentile_rank(series, current_value, lookback=365):
    """計算當前數值在過去 lookback 天資料中的百分位。

    回傳 0-100 的浮點數，表示有多少比例的歷史值 <= current_value。
    """
    recent = series.dropna().tail(lookback)
    if len(recent) == 0:
        return 50.0  # 無資料時回傳中位數

    count_below = (recent <= current_value).sum()
    percentile = count_below / len(recent) * 100
    return float(percentile)


def calc_correlation(df_a, df_b, window):
    """計算兩個幣種日報酬率的 Pearson 相關係數。

    使用最近 window 天的日報酬率計算相關係數。
    結果 clip 至 [-1, 1]。
    """
    returns_a = df_a["close"].pct_change(fill_method=None).dropna().tail(window)
    returns_b = df_b["close"].pct_change(fill_method=None).dropna().tail(window)

    # 對齊兩個序列（取共同索引）
    aligned_a, aligned_b = returns_a.align(returns_b, join="inner")

    if len(aligned_a) < 2:
        return 0.0
    if aligned_a.nunique(dropna=True) <= 1 or aligned_b.nunique(dropna=True) <= 1:
        return 0.0

    corr = aligned_a.corr(aligned_b)

    # 處理 NaN（例如其中一方完全無變化）
    if pd.isna(corr):
        return 0.0

    return float(np.clip(corr, -1.0, 1.0))


def compute_quant(symbol, features, window, related_claim, compare_symbol=None):
    """計算指定的技術指標。主入口函式。

    步驟：
      1. 取得該幣種的價格資料（呼叫 price.get_price_ohlcv）
      2. 依 features 清單逐一計算對應指標
      3. 每個指標同時計算「當前值」與「在歷史資料中的百分位」
    features 可能包含：atr_pct、bollinger_bandwidth、adx、range_ratio、
                      volume_zscore、realized_vol、correlation
    回傳：統一格式 dict
    """
    try:
        from tools.price import get_price_ohlcv

        # 計算需要的起始日期：window + 365 天（用於百分位計算）
        lookback_days = window + 365
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        # 取得主幣種價格資料
        price_result = get_price_ohlcv(symbol, start_date, end_date, related_claim)
        if isinstance(price_result, dict) and "error" in price_result:
            return {
                "error": f"Failed to get price data for {symbol}: {price_result['error']}",
                "source": "local_pandas_computation",
                "content_reference": {},
            }

        # price_result 應該包含 raw 欄位中的 DataFrame 或直接是 DataFrame
        if isinstance(price_result, dict) and "raw" in price_result:
            raw_data = price_result["raw"]
            if isinstance(raw_data, pd.DataFrame):
                df = raw_data
            else:
                df = pd.DataFrame(raw_data)
        elif isinstance(price_result, pd.DataFrame):
            df = price_result
        else:
            return {
                "error": f"Unexpected price data format for {symbol}",
                "source": "local_pandas_computation",
                "content_reference": {},
            }

        if df.empty or len(df) < window:
            return {
                "error": f"Insufficient price data for {symbol}: got {len(df)} rows, need at least {window}",
                "source": "local_pandas_computation",
                "content_reference": {},
            }

        # 取得比較幣種資料（如需要）
        df_compare = None
        if compare_symbol and "correlation" in features:
            compare_result = get_price_ohlcv(compare_symbol, start_date, end_date, related_claim)
            if isinstance(compare_result, dict) and "error" in compare_result:
                # 相關係數無法計算，但其他指標仍可繼續
                pass
            elif isinstance(compare_result, dict) and "raw" in compare_result:
                raw_compare = compare_result["raw"]
                if isinstance(raw_compare, pd.DataFrame):
                    df_compare = raw_compare
                else:
                    df_compare = pd.DataFrame(raw_compare)
            elif isinstance(compare_result, pd.DataFrame):
                df_compare = compare_result

        # 逐一計算各指標
        results = {}
        price_ref = price_result.get("content_reference", {}) if isinstance(price_result, dict) else {}
        actual_start = str(df["date"].iloc[0])
        actual_end = str(df["date"].iloc[-1])
        content_ref = {
            "symbol": symbol,
            "window": window,
            "input_range": f"{actual_start}~{actual_end}",
            "as_of": actual_end,
            "price_source": price_result.get("source", "") if isinstance(price_result, dict) else "",
            "price_query": price_ref.get("query_endpoint", ""),
            "human_url": price_ref.get("human_url", f"https://www.binance.com/en/trade/{symbol}_USDT?type=spot"),
            "indicators": {},
        }

        for feature in features:
            try:
                if feature == "atr_pct":
                    atr_pct_series = calc_atr_pct(df, window)
                    last_value = atr_pct_series.iloc[-1]
                    value = 0.0 if pd.isna(last_value) or not np.isfinite(last_value) else float(last_value)
                    percentile = calc_percentile_rank(atr_pct_series, value)

                elif feature == "bollinger_bandwidth":
                    bw_series = calc_bollinger_bandwidth(df, window) * 100
                    last_value = bw_series.iloc[-1]
                    value = 0.0 if pd.isna(last_value) or not np.isfinite(last_value) else float(last_value)
                    percentile = calc_percentile_rank(bw_series, value)

                elif feature == "adx":
                    adx_series = calc_adx(df, window)
                    last_value = adx_series.iloc[-1]
                    value = 0.0 if pd.isna(last_value) or not np.isfinite(last_value) else float(last_value)
                    percentile = calc_percentile_rank(adx_series, value)

                elif feature == "volume_zscore":
                    volume = df["volume"].astype(float)
                    recent_vol = volume.tail(window)
                    mean_vol = recent_vol.mean()
                    std_vol = recent_vol.std()
                    current_vol = volume.iloc[-1]
                    if std_vol == 0 or pd.isna(std_vol):
                        value = 0.0
                    else:
                        value = float((current_vol - mean_vol) / std_vol)
                    # Z-score 的百分位：用歷史 rolling z-score
                    rolling_mean = volume.rolling(window=window).mean()
                    rolling_std = volume.rolling(window=window).std()
                    zscore_series = (volume - rolling_mean) / rolling_std.replace(0, np.nan)
                    percentile = calc_percentile_rank(zscore_series, value)

                elif feature == "realized_vol":
                    close = df["close"]
                    daily_returns = close.pct_change(fill_method=None).dropna()
                    recent_returns = daily_returns.tail(window)
                    value = float(recent_returns.std() * np.sqrt(365) * 100)
                    # 歷史 realized vol 序列
                    rv_series = daily_returns.rolling(window=window).std() * np.sqrt(365) * 100
                    percentile = calc_percentile_rank(rv_series, value)

                elif feature == "correlation":
                    if df_compare is not None and not df_compare.empty:
                        value = calc_correlation(df, df_compare, window)
                        percentile = 50.0  # 相關係數的百分位意義不大，給中性值
                    else:
                        value = None
                        percentile = None

                elif feature == "range_ratio":
                    # Range Ratio: (最近 window 天最高 - 最低) / 最新收盤價 * 100
                    close = df["close"]
                    high = df["high"]
                    low = df["low"]
                    recent_high = high.tail(window).max()
                    recent_low = low.tail(window).min()
                    last_close = close.iloc[-1]
                    value = float((recent_high - recent_low) / last_close * 100)
                    # 歷史 range ratio 序列
                    rolling_high = high.rolling(window=window).max()
                    rolling_low = low.rolling(window=window).min()
                    rr_series = (rolling_high - rolling_low) / close * 100
                    percentile = calc_percentile_rank(rr_series, value)

                else:
                    # 不支援的指標，跳過
                    results[feature] = {"value": None, "percentile": None, "note": "unsupported feature"}
                    continue

                results[feature] = {"value": round(value, 4) if value is not None else None, "percentile": round(percentile, 1) if percentile is not None else None}
                content_ref["indicators"][feature] = results[feature]

            except Exception as e:
                results[feature] = {"value": None, "percentile": None, "error": str(e)}
                content_ref["indicators"][feature] = results[feature]

        # 組裝摘要
        summary_parts = []
        for feat, res in results.items():
            if res.get("value") is not None:
                summary_parts.append(f"{feat}={res['value']} (P{res.get('percentile', '?')})")
            elif res.get("error"):
                summary_parts.append(f"{feat}=error({res['error']})")
            else:
                summary_parts.append(f"{feat}=N/A")
        summary = (
            f"{symbol} {window}d indicators（輸入資料 {actual_start}~{actual_end}，截至 {actual_end}）: "
            + ", ".join(summary_parts)
        )

        return {
            "raw": results,
            "source": "local_pandas_computation",
            "content_reference": content_ref,
            "summary": summary,
        }

    except Exception as e:
        return {
            "error": f"[compute_quant] {type(e).__name__}: {str(e)}",
            "source": "local_pandas_computation",
            "content_reference": {},
        }


# ---- C1 v1.0 品質契約與決定性異常偵測 ----
_ORIGINAL_COMPUTE_QUANT = compute_quant


def detect_quant_anomalies(results, window, as_of):
    """依 config 門檻把已計算指標轉成 A1-A4 anomaly_flags。"""
    import config
    from tools.quality import make_anomaly_flag

    flags = []

    def add_if(feature, signal_id, name, low=None, high=None, unit=""):
        item = results.get(feature, {}) if isinstance(results, dict) else {}
        value = item.get("value")
        percentile = item.get("percentile")
        if value is None or percentile is None:
            return
        direction = None
        threshold = None
        if low is not None and percentile <= low:
            direction = "low"
            threshold = f"percentile <= {low:g}"
        elif high is not None and percentile >= high:
            direction = "high"
            threshold = f"percentile >= {high:g}"
        if direction is None:
            return
        flags.append(make_anomaly_flag(
            signal_id=signal_id,
            name=name,
            severity="significant",
            direction=direction,
            value=value,
            unit=unit,
            percentile=percentile,
            threshold=threshold,
            window=f"{window}d",
            as_of=as_of,
            message=f"{name}={value}（歷史第 {percentile} 百分位），達 {threshold} 門檻",
        ))

    thresholds = config.ANOMALY_THRESHOLDS
    add_if(
        "volume_zscore", "A1", "量能異常",
        low=thresholds["volume_percentile_low"],
        high=thresholds["volume_percentile_high"],
        unit="z-score",
    )
    add_if(
        "bollinger_bandwidth", "A2", "波動壓縮／爆發",
        low=thresholds["bollinger_percentile_low"],
        high=thresholds["bollinger_percentile_high"],
        unit="%",
    )
    add_if(
        "atr_pct", "A3", "真實波幅極端",
        high=thresholds["atr_percentile_high"],
        unit="%",
    )
    add_if(
        "adx", "A4", "趨勢強度極端",
        low=thresholds["adx_percentile_low"],
        high=thresholds["adx_percentile_high"],
        unit="index",
    )
    return flags


def compute_quant(symbol, features, window, related_claim, compare_symbol=None):
    """C1 v1.0 包裝：補齊品質、單位、相容欄位與 A1-A4。"""
    import config
    from tools.quality import standardize_tool_result

    symbol_upper = str(symbol).upper().strip()
    compare_upper = str(compare_symbol).upper().strip() if compare_symbol else None
    result = _ORIGINAL_COMPUTE_QUANT(
        symbol_upper, features, window, related_claim, compare_upper
    )
    reference = result.get("content_reference", {}) if isinstance(result, dict) else {}
    indicators = result.get("raw", {}) if isinstance(result, dict) else {}

    # 舊測試與舊消費端曾直接讀 content_reference[feature]；保留相容別名。
    if isinstance(reference, dict):
        for feature, item in indicators.items() if isinstance(indicators, dict) else []:
            enriched = dict(item) if isinstance(item, dict) else {"value": item}
            enriched.setdefault("window", window)
            reference.setdefault(feature, enriched)
        if isinstance(result, dict):
            result["content_reference"] = reference

    unit_map = {
        "atr_pct": "%",
        "bollinger_bandwidth": "%",
        "adx": "index",
        "volume_zscore": "z-score",
        "realized_vol": "% annualized",
        "correlation": "coefficient",
        "range_ratio": "%",
    }
    price_reference = reference.get("as_of")
    notes = []
    comparability = "comparable"
    if "correlation" in features and not compare_upper:
        comparability = "limited"
        notes.append("未提供 compare_symbol，correlation 無法計算")

    normalized = standardize_tool_result(
        result,
        provider="Local deterministic pandas",
        endpoint="local://tools/quant/compute_quant",
        symbol=symbol_upper,
        pair=f"{symbol_upper}USDT",
        timeframe="1d",
        window=f"{window}d",
        unit={feature: unit_map.get(feature, "unknown") for feature in features},
        as_of=price_reference,
        max_age_seconds=config.FRESHNESS_THRESHOLDS_SECONDS["quant_daily"],
        comparability_status=comparability,
        comparability_notes=notes,
    )
    if normalized.get("status") != "error":
        normalized["anomaly_flags"] = detect_quant_anomalies(
            normalized.get("raw", {}), window, price_reference
        )

    # ---- Relative-strength series output ----
    # Only compute if compare_symbol provided AND relevant features requested
    if compare_upper and normalized.get("status") != "error" and (
        "relative_strength" in features or "correlation" in features
    ):
        try:
            # Lazy imports to avoid circular dependencies
            from tools.series_utils import (
                extract_price_series,
                build_series_envelope,
                inner_join_series,
                calc_relative_strength,
                normalize_series,
            )
            from tools.price import get_price_ohlcv

            # Use the same date range as the original computation
            lookback_days = window + 365
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start_date = (
                datetime.now(timezone.utc) - timedelta(days=lookback_days)
            ).strftime("%Y-%m-%d")

            # Fetch both symbols' price data
            price_a = get_price_ohlcv(
                symbol_upper, start_date, end_date, related_claim
            )
            price_b = get_price_ohlcv(
                compare_upper, start_date, end_date, related_claim
            )

            # Determine providers from source URLs for comparability
            source_a = (
                price_a.get("source", "") if isinstance(price_a, dict) else ""
            )
            source_b = (
                price_b.get("source", "") if isinstance(price_b, dict) else ""
            )

            def _detect_provider(source_str):
                s = source_str.lower()
                if "coingecko" in s:
                    return "coingecko"
                if "binance" in s:
                    return "binance"
                return "baseline_csv"

            provider_a = _detect_provider(source_a)
            provider_b = _detect_provider(source_b)
            same_provider = provider_a == provider_b

            # Extract OHLCV records from raw results
            # price.py keeps raw as a list of OHLCV dicts; series is at top level
            def _extract_ohlcv(price_result):
                raw = price_result.get("raw", []) if isinstance(price_result, dict) else []
                if isinstance(raw, list):
                    return raw
                if isinstance(raw, dict):
                    return raw.get("ohlcv", [])
                return []

            raw_records_a = _extract_ohlcv(price_a)
            raw_records_b = _extract_ohlcv(price_b)

            # Only proceed if both fetches succeeded (non-empty records)
            if raw_records_a and raw_records_b:
                series_a = extract_price_series(raw_records_a, max_days=90)
                series_b = extract_price_series(raw_records_b, max_days=90)

                # Compute relative strength
                rs_points = calc_relative_strength(series_a, series_b)

                # Build comparability metadata
                rs_comparability_notes = []
                if not same_provider:
                    rs_comparability_notes.append(
                        f"Mixed providers: {symbol_upper} from {provider_a}, "
                        f"{compare_upper} from {provider_b}"
                    )

                # Handle edge case: fewer than 2 shared dates
                if len(rs_points) < 2:
                    rs_comparability_notes.append(
                        "Fewer than 2 shared dates; relative strength series unavailable"
                    )
                    rs_envelope = None
                else:
                    rs_as_of = rs_points[-1][0]  # Latest date
                    rs_envelope = build_series_envelope(
                        rs_points,
                        unit=f"{symbol_upper}/{compare_upper}",
                        provider="Local deterministic pandas",
                        pair=f"{symbol_upper}USDT/{compare_upper}USDT",
                        timeframe="1d",
                        as_of=rs_as_of,
                        comparability="comparable" if same_provider else "limited",
                        comparability_notes=rs_comparability_notes or None,
                    )

                # Correlation scalar (already computed by _ORIGINAL_COMPUTE_QUANT)
                raw_indicators = normalized.get("raw", {})
                corr_value = None
                if isinstance(raw_indicators, dict):
                    corr_item = raw_indicators.get("correlation", {})
                    if isinstance(corr_item, dict):
                        corr_value = corr_item.get("value")

                # Inject series at top level (consistent adapter key for Report/C7)
                normalized["series"] = {
                    "relative_strength": rs_envelope,
                    "correlation_metadata": {
                        "value": corr_value,
                        "type": "scalar",
                        "unit": "coefficient",
                        "pair": f"{symbol_upper}/{compare_upper}",
                        "window": f"{window}d",
                        "note": "Pearson correlation of daily returns",
                    },
                }

                # Update summary with latest RS value and change (NOT full series)
                if rs_points and len(rs_points) >= 2:
                    latest_rs = rs_points[-1][1]
                    prev_rs = rs_points[-2][1]
                    rs_change = latest_rs - prev_rs
                    rs_summary_part = (
                        f" | RS({symbol_upper}/{compare_upper})="
                        f"{latest_rs:.6f} (Δ{rs_change:+.6f})"
                    )
                    if corr_value is not None:
                        rs_summary_part += f", corr={corr_value:.4f}"
                    normalized["summary"] = (
                        normalized.get("summary", "") + rs_summary_part
                    )
                elif rs_points and len(rs_points) == 1:
                    latest_rs = rs_points[0][1]
                    rs_summary_part = (
                        f" | RS({symbol_upper}/{compare_upper})={latest_rs:.6f}"
                    )
                    if corr_value is not None:
                        rs_summary_part += f", corr={corr_value:.4f}"
                    normalized["summary"] = (
                        normalized.get("summary", "") + rs_summary_part
                    )

        except Exception:
            # If series computation fails, do NOT fail the whole quant result.
            # Just skip adding series data — the core indicators are still valid.
            pass

    return normalized
