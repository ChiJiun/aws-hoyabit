"""
quant.py — 技術指標計算工具

這個工具不呼叫任何外部 API，純粹是本地計算。
存在的理由：所有數字必須由程式決定性地算出來，不能讓模型心算。
模型心算數字是現場 Demo 時最容易被評審驗證出錯的地方。
"""

import pandas as pd
import numpy as np

import storage


def compute_quant(symbol, features, window, related_claim, compare_symbol=None):
    """計算指定的技術指標，每個指標同時附帶歷史百分位排名。

    Args:
        symbol: 幣種代號（如 "BTC"）
        features: 要計算的指標清單（如 ["atr_pct", "adx", "volume_zscore"]）
        window: 計算視窗（天數）
        related_claim: LLM 提供的取數目的說明
        compare_symbol: 比較幣種代號（僅 correlation 指標需要）

    Returns:
        統一格式 dict（成功時含 raw/source/content_reference/summary，失敗時含 error）
    """
    try:
        # 1. 取得主要幣種的 OHLCV 資料
        df = storage.read_baseline_csv(symbol)

        # 若需要計算 correlation 且有比較幣種，讀取比較幣種資料
        df_compare = None
        if compare_symbol is not None and "correlation" in features:
            df_compare = storage.read_baseline_csv(compare_symbol)

        # 2. 依 features 清單逐一計算
        raw_results = {}
        content_ref = {}
        summary_parts = []

        for feature in features:
            if feature == "atr_pct":
                series = calc_atr_pct(df, window)
                current_value = float(series.dropna().iloc[-1])
                percentile = calc_percentile_rank(series, current_value)
                raw_results[feature] = {"value": current_value, "percentile": percentile}
                content_ref[feature] = {"value": current_value, "percentile": percentile, "window": window}
                summary_parts.append(f"ATR% = {current_value:.2f} (百分位 {percentile:.0f})")

            elif feature == "bollinger_bandwidth":
                series = calc_bollinger_bandwidth(df, window)
                current_value = float(series.dropna().iloc[-1])
                percentile = calc_percentile_rank(series, current_value)
                raw_results[feature] = {"value": current_value, "percentile": percentile}
                content_ref[feature] = {"value": current_value, "percentile": percentile, "window": window}
                summary_parts.append(f"布林帶寬 = {current_value:.4f} (百分位 {percentile:.0f})")

            elif feature == "adx":
                series = calc_adx(df, window)
                current_value = float(series.dropna().iloc[-1])
                percentile = calc_percentile_rank(series, current_value)
                raw_results[feature] = {"value": current_value, "percentile": percentile}
                content_ref[feature] = {"value": current_value, "percentile": percentile, "window": window}
                summary_parts.append(f"ADX = {current_value:.2f} (百分位 {percentile:.0f})")

            elif feature == "volume_zscore":
                vol = df["volume"]
                rolling_mean = vol.rolling(window=window).mean()
                rolling_std = vol.rolling(window=window).std()
                zscore_series = (vol - rolling_mean) / rolling_std
                current_value = float(zscore_series.dropna().iloc[-1])
                percentile = calc_percentile_rank(zscore_series, current_value)
                raw_results[feature] = {"value": current_value, "percentile": percentile}
                content_ref[feature] = {"value": current_value, "percentile": percentile, "window": window}
                summary_parts.append(f"成交量Z-score = {current_value:.2f} (百分位 {percentile:.0f})")

            elif feature == "realized_vol":
                daily_returns = df["close"].pct_change()
                realized_vol_series = daily_returns.rolling(window=window).std() * np.sqrt(365)
                current_value = float(realized_vol_series.dropna().iloc[-1])
                percentile = calc_percentile_rank(realized_vol_series, current_value)
                raw_results[feature] = {"value": current_value, "percentile": percentile}
                content_ref[feature] = {"value": current_value, "percentile": percentile, "window": window}
                summary_parts.append(f"已實現波動率 = {current_value:.4f} (百分位 {percentile:.0f})")

            elif feature == "correlation":
                if compare_symbol is None or df_compare is None:
                    raw_results[feature] = {"value": None, "percentile": None}
                    content_ref[feature] = {"value": None, "percentile": None, "window": window}
                    summary_parts.append("相關係數 = N/A (未指定比較幣種)")
                else:
                    corr_value = calc_correlation(df, df_compare, window)
                    raw_results[feature] = {"value": corr_value, "percentile": None}
                    content_ref[feature] = {"value": corr_value, "percentile": None, "window": window}
                    summary_parts.append(f"{symbol}/{compare_symbol} 相關係數 = {corr_value:.4f}")

        # 3. 組裝統一格式回傳
        summary_text = "技術指標計算結果：" + "、".join(summary_parts)

        return {
            "raw": raw_results,
            "source": "local_pandas_computation",
            "content_reference": content_ref,
            "summary": summary_text,
        }

    except Exception as e:
        return {
            "error": f"[compute_quant] {type(e).__name__}: {str(e)}",
            "source": "local_pandas_computation",
            "content_reference": {},
        }


def calc_atr_pct(df, window):
    # 功能：計算 ATR（平均真實區間）並轉成佔價格的百分比。
    # 用途：衡量波動率，是判斷「盤整」的核心指標之一。
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    # True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # ATR = rolling mean of TR over the specified window
    atr = tr.rolling(window=window).mean()

    # Convert to percentage of the current close price
    atr_pct = (atr / close) * 100
    return atr_pct


def calc_adx(df, window):
    # 功能：計算 ADX（平均趨向指標）。
    # 用途：衡量趨勢強度。一般以低於 20 視為無明確趨勢，可支持盤整判斷。
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    # +DM / -DM
    plus_dm = high - prev_high
    minus_dm = prev_low - low
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    # True Range
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder's smoothing (EWM with alpha = 1/window)
    alpha = 1.0 / window
    smoothed_tr = tr.ewm(alpha=alpha, adjust=False).mean()
    smoothed_plus_dm = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    smoothed_minus_dm = minus_dm.ewm(alpha=alpha, adjust=False).mean()

    # +DI / -DI
    plus_di = 100 * smoothed_plus_dm / smoothed_tr
    minus_di = 100 * smoothed_minus_dm / smoothed_tr

    # DX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)

    # ADX = smoothed DX
    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    return adx


def calc_bollinger_bandwidth(df, window):
    # 功能：計算布林帶寬（上下軌距離佔中軌的比例）。
    # 用途：帶寬收窄代表波動率壓縮，常見於盤整或突破前的醞釀期。
    close = df["close"]

    sma = close.rolling(window=window).mean()
    std = close.rolling(window=window).std()

    upper = sma + 2 * std
    lower = sma - 2 * std

    bandwidth = (upper - lower) / sma
    return bandwidth


def calc_percentile_rank(series, current_value, lookback=365):
    # 功能：計算當前數值在過去 lookback 天資料中的百分位。
    # 這是把「絕對數值」轉成「相對歷史位置」的關鍵，讓推論有比較基準。

    # 取最後 lookback 筆並去除 NaN
    window = series.tail(lookback).dropna()

    # 邊界：若無有效資料則回傳 50（中位數假設）
    if len(window) == 0:
        return 50.0

    # 計算百分位：有多少比例的歷史值 <= current_value
    rank = (window <= current_value).sum() / len(window) * 100

    # 確保結果落在 [0, 100]
    return float(np.clip(rank, 0, 100))


def calc_correlation(df_a, df_b, window):
    # 功能：計算兩個幣種報酬率的相關係數。
    # 用途：比較分析題型（範例三）會需要，用來說明兩者風險敞口的差異。

    # 計算日報酬率
    returns_a = df_a["close"].pct_change().dropna()
    returns_b = df_b["close"].pct_change().dropna()

    # 取最後 window 天的報酬率
    returns_a = returns_a.tail(window)
    returns_b = returns_b.tail(window)

    # 邊界處理：資料不足或標準差為零（全同值）時回傳中性相關
    if len(returns_a) < 2 or len(returns_b) < 2:
        return 0.0

    # 計算 Pearson 相關係數
    corr = returns_a.corr(returns_b)

    # NaN 處理（例如其中一方標準差為零）
    if pd.isna(corr):
        return 0.0

    # 夾值確保結果必定落在 [-1, 1]（防止浮點數溢出邊界）
    return float(np.clip(corr, -1.0, 1.0))