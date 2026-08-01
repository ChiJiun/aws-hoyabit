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
    """計算 ATR（平均真實區間）並轉成佔價格的百分比。

    True Range = max(H-L, |H-prevC|, |L-prevC|)
    ATR = EWM(TR, span=window)
    回傳最後一筆 ATR / 最後收盤價 * 100
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(span=window, adjust=False).mean()

    last_atr = atr.iloc[-1]
    last_close = close.iloc[-1]

    return last_atr / last_close * 100


def calc_bollinger_bandwidth(df, window):
    """計算布林帶寬（上下軌距離佔中軌的比例）。

    Mid = SMA(close, window)
    Upper = Mid + 2 * std
    Lower = Mid - 2 * std
    BW = (Upper - Lower) / Mid * 100
    回傳最後一筆 BW 值。
    """
    close = df["close"]
    mid = close.rolling(window=window).mean()
    std = close.rolling(window=window).std()

    upper = mid + 2 * std
    lower = mid - 2 * std
    bandwidth = (upper - lower) / mid * 100

    return bandwidth.iloc[-1]


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

    return adx.iloc[-1]


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
    returns_a = df_a["close"].pct_change().dropna().tail(window)
    returns_b = df_b["close"].pct_change().dropna().tail(window)

    # 對齊兩個序列（取共同索引）
    aligned_a, aligned_b = returns_a.align(returns_b, join="inner")

    if len(aligned_a) < 2:
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
                    value = calc_atr_pct(df, window)
                    # 計算歷史 ATR% 序列用於百分位
                    high = df["high"]
                    low = df["low"]
                    close = df["close"]
                    prev_close = close.shift(1)
                    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
                    atr_series = tr.ewm(span=window, adjust=False).mean()
                    atr_pct_series = atr_series / close * 100
                    percentile = calc_percentile_rank(atr_pct_series, value)

                elif feature == "bollinger_bandwidth":
                    value = calc_bollinger_bandwidth(df, window)
                    # 計算歷史 BW 序列用於百分位
                    close = df["close"]
                    mid = close.rolling(window=window).mean()
                    std = close.rolling(window=window).std()
                    bw_series = (mid + 2 * std - (mid - 2 * std)) / mid * 100
                    percentile = calc_percentile_rank(bw_series, value)

                elif feature == "adx":
                    value = calc_adx(df, window)
                    # ADX 百分位：重建 ADX 序列
                    high = df["high"]
                    low = df["low"]
                    close = df["close"]
                    plus_dm = high.diff()
                    minus_dm_raw = -low.diff()
                    plus_dm = plus_dm.where((plus_dm > minus_dm_raw) & (plus_dm > 0), 0.0)
                    minus_dm_raw = minus_dm_raw.where((minus_dm_raw > plus_dm) & (minus_dm_raw > 0), 0.0)
                    prev_c = close.shift(1)
                    tr = pd.concat([high - low, (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
                    atr_s = tr.ewm(span=window, adjust=False).mean()
                    plus_dm_s = plus_dm.ewm(span=window, adjust=False).mean()
                    minus_dm_s = minus_dm_raw.ewm(span=window, adjust=False).mean()
                    plus_di = (plus_dm_s / atr_s) * 100
                    minus_di = (minus_dm_s / atr_s) * 100
                    di_sum = plus_di + minus_di
                    di_diff = (plus_di - minus_di).abs()
                    dx = (di_diff / di_sum.replace(0, np.nan)) * 100
                    adx_series = dx.ewm(span=window, adjust=False).mean()
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
                    daily_returns = close.pct_change().dropna()
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
