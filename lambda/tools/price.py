"""
price.py — 價格與 OHLCV 資料工具

資料來源：賽方基準 CSV（S3）＋ Binance 公開 API／CoinGecko（補即時）
"""

import time
from datetime import datetime, timezone

import pandas as pd
import requests

import evidence
import storage
from config import BASELINE_END_DATE, COINGECKO_API_KEY

# CoinGecko 幣種 ID 對照表
_COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
}


def get_price_ohlcv(symbol, start_date, end_date, related_claim):
    """取得指定幣種在指定期間的日線 OHLCV 資料。

    步驟：
      1. storage.read_baseline_csv(symbol) 讀取賽方基準資料
      2. 檢查 end_date 是否超過 BASELINE_END_DATE（2026-05-31）
      3. 若超過，呼叫 fetch_recent_from_exchange() 補齊缺口
      4. 呼叫 check_data_seam() 驗證兩段資料的接縫
      5. 篩選出 start_date ~ end_date 的區間

    回傳：統一格式 dict（成功）或 error dict（失敗）
    """
    pair = f"{symbol}USDT"
    source_url = f"baseline/{pair}_daily_ohlcv.csv"
    start_time = time.time()

    try:

        # 1. 讀取基準 CSV
        baseline_df = storage.read_baseline_csv(symbol)

        # 2. 判斷是否需要補即時資料
        recent_df = pd.DataFrame()
        needs_recent = end_date > BASELINE_END_DATE

        if needs_recent:
            # 從 BASELINE_END_DATE 的隔天開始補即時資料
            from_date = BASELINE_END_DATE
            try:
                recent_df = fetch_recent_from_exchange(symbol, from_date)
                source_url = f"https://api.binance.com/api/v3/klines?symbol={pair}&interval=1d"
            except Exception:
                # Binance 失敗，使用 CoinGecko 作為備用來源
                try:
                    recent_df = _fetch_recent_from_coingecko(symbol, from_date, end_date)
                    source_url = f"https://api.coingecko.com/api/v3/coins/{_COINGECKO_IDS.get(symbol, symbol.lower())}/ohlc"
                except Exception as cg_err:
                    # 兩個來源都失敗，僅使用基準資料
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    evidence.log_execution_step(
                        tool_name="get_price_ohlcv",
                        status="warning",
                        elapsed_ms=elapsed_ms,
                        note=f"即時資料取得失敗（Binance + CoinGecko），僅使用基準資料: {cg_err}",
                    )
                    recent_df = pd.DataFrame()

            # 4. 驗證接縫（只有在取得到即時資料時才需要）
            if not recent_df.empty:
                check_data_seam(baseline_df, recent_df)

        # 5. 拼接並篩選日期範圍
        if not recent_df.empty:
            combined_df = pd.concat([baseline_df, recent_df], ignore_index=True)
            # 移除重複日期（保留基準資料的版本）
            combined_df = combined_df.drop_duplicates(subset=["date"], keep="first")
        else:
            combined_df = baseline_df

        # 篩選日期範圍
        combined_df = combined_df[
            (combined_df["date"] >= start_date) & (combined_df["date"] <= end_date)
        ].reset_index(drop=True)

        # 組裝回傳結果
        rows = len(combined_df)
        if rows == 0:
            return {
                "error": f"[get_price_ohlcv] 在 {start_date}~{end_date} 範圍內無 {pair} 資料",
                "source": source_url,
                "content_reference": {},
            }

        actual_start = combined_df["date"].iloc[0]
        actual_end = combined_df["date"].iloc[-1]

        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="get_price_ohlcv",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"{pair} {actual_start}~{actual_end}, {rows} rows",
        )

        return {
            "raw": combined_df.to_dict(orient="records"),
            "source": source_url,
            "content_reference": {
                "pair": pair,
                "range": f"{actual_start}~{actual_end}",
                "rows": rows,
            },
            "summary": (
                f"{pair} 日線 OHLCV：{actual_start} 至 {actual_end}，共 {rows} 筆。"
                f"最新收盤價 {combined_df['close'].iloc[-1]:.4f}"
            ),
        }

    except Exception as e:
        # Property 12: 永不拋錯，失敗時回傳 error dict
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="get_price_ohlcv",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[get_price_ohlcv] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def _fetch_recent_from_coingecko(symbol: str, from_date: str, to_date: str) -> pd.DataFrame:
    """從 CoinGecko API 取得近期 OHLC 資料作為 Binance 的備用來源。

    Parameters
    ----------
    symbol : str
        幣種代碼，如 "BTC", "SOL"。
    from_date : str
        起始日期（YYYY-MM-DD）。
    to_date : str
        結束日期（YYYY-MM-DD）。

    Returns
    -------
    pd.DataFrame
        欄位：date, open, high, low, close, volume。
    """
    coin_id = _COINGECKO_IDS.get(symbol, symbol.lower())

    # 將日期轉為 Unix 時間戳
    from_ts = int(datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    to_ts = int(datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())

    # 使用 market_chart/range 端點取得歷史資料
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
    params = {
        "vs_currency": "usd",
        "from": from_ts,
        "to": to_ts,
    }
    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # CoinGecko market_chart/range 回傳 prices, market_caps, total_volumes
    # prices 格式: [[timestamp_ms, price], ...]
    prices = data.get("prices", [])
    volumes = data.get("total_volumes", [])

    # 按天聚合（CoinGecko 可能回傳多個小時級數據點）
    daily_data = {}
    for ts_ms, price in prices:
        date_str = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if date_str not in daily_data:
            daily_data[date_str] = {"open": price, "high": price, "low": price, "close": price}
        else:
            daily_data[date_str]["high"] = max(daily_data[date_str]["high"], price)
            daily_data[date_str]["low"] = min(daily_data[date_str]["low"], price)
            daily_data[date_str]["close"] = price  # 最後一筆作為收盤

    # 填入成交量
    daily_volumes = {}
    for ts_ms, vol in volumes:
        date_str = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if date_str not in daily_volumes:
            daily_volumes[date_str] = vol
        else:
            daily_volumes[date_str] = max(daily_volumes[date_str], vol)

    rows = []
    for date_str in sorted(daily_data.keys()):
        d = daily_data[date_str]
        rows.append({
            "date": date_str,
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "volume": float(daily_volumes.get(date_str, 0.0)),
        })

    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    return df


def fetch_recent_from_exchange(symbol: str, from_date: str) -> pd.DataFrame:
    """從 Binance 公開 API 取得基準資料截止日之後的最新日線 OHLCV。

    Parameters
    ----------
    symbol : str
        幣種代碼，如 "BTC", "SOL"。
    from_date : str
        起始日期（YYYY-MM-DD），會取該日（含）之後的日線資料。

    Returns
    -------
    pd.DataFrame
        欄位與基準 CSV 相同：date, open, high, low, close, volume。
        date 為 YYYY-MM-DD 字串，其餘為 float。
    """
    # 將 from_date 轉換為毫秒時間戳（Binance API 需要）
    start_dt = datetime.strptime(from_date, "%Y-%m-%d")
    start_ms = int(start_dt.timestamp() * 1000)

    # 呼叫 Binance 公開 API 取得日線 klines
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": f"{symbol}USDT",
        "interval": "1d",
        "startTime": start_ms,
        "limit": 1000,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    klines = resp.json()

    # 解析 klines 回應為 DataFrame
    # Binance kline 格式: [open_time, open, high, low, close, volume, ...]
    rows = []
    for k in klines:
        open_time_ms = k[0]
        date_str = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append({
            "date": date_str,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })

    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    return df


def check_data_seam(baseline_df, recent_df):
    # 功能：檢查基準資料與即時資料的接縫是否一致。
    # 實作：找出兩段資料日期重疊的部分，比對收盤價差異百分比。
    # 為什麼做這件事：主動揭露資料拼接點與校驗結果，正面回應命題對
    #                「可回溯的證據管理」的要求，也避免指標計算失真。
    # 回傳：(是否通過, 重疊日數, 最大價差百分比)

    THRESHOLD_PCT = 1.0  # 最大允許差異百分比

    start_time = time.time()

    # 找出重疊日期
    baseline_dates = set(baseline_df["date"].values)
    recent_dates = set(recent_df["date"].values)
    overlap_dates = sorted(baseline_dates & recent_dates)

    overlap_count = len(overlap_dates)

    # 無重疊日期：視為通過
    if overlap_count == 0:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="check_data_seam",
            status="success",
            elapsed_ms=elapsed_ms,
            note="無重疊日期，跳過接縫校驗",
        )
        return (True, 0, 0.0)

    # 計算每個重疊日期的收盤價差異百分比
    baseline_close = baseline_df.set_index("date")["close"]
    recent_close = recent_df.set_index("date")["close"]

    max_diff_pct = 0.0
    for d in overlap_dates:
        b_close = float(baseline_close[d])
        r_close = float(recent_close[d])
        if b_close == 0:
            continue
        diff_pct = abs(b_close - r_close) / abs(b_close) * 100
        if diff_pct > max_diff_pct:
            max_diff_pct = diff_pct

    passed = max_diff_pct <= THRESHOLD_PCT
    elapsed_ms = int((time.time() - start_time) * 1000)

    evidence.log_execution_step(
        tool_name="check_data_seam",
        status="success" if passed else "warning",
        elapsed_ms=elapsed_ms,
        note=f"重疊日數={overlap_count}, 最大價差={max_diff_pct:.4f}%",
    )

    return (passed, overlap_count, max_diff_pct)


def get_orderbook_depth(symbol, related_claim):
    """取得 Binance Spot 盤口深度快照，計算 ±2% 範圍內的累積掛單量。

    Args:
        symbol: 幣種代碼（BTC, ETH, SOL, BNB, XRP）
        related_claim: Agent 說明取數目的

    Returns:
        Contract C1 dict or error dict
    """
    symbol_upper = symbol.upper()
    pair = f"{symbol_upper}USDT"
    source_url = f"https://api.binance.com/api/v3/depth?symbol={pair}&limit=1000"
    start_time = time.time()

    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/depth",
            params={"symbol": pair, "limit": 1000},
            headers={"User-Agent": "HoyabitAgent/1.0"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        bids = data["bids"]  # [[price, qty], ...]
        asks = data["asks"]  # [[price, qty], ...]

        # 計算 ±2% 深度
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        bid_threshold = best_bid * 0.98
        ask_threshold = best_ask * 1.02

        bid_depth_2pct = sum(
            float(qty) for price, qty in bids if float(price) >= bid_threshold
        )
        ask_depth_2pct = sum(
            float(qty) for price, qty in asks if float(price) <= ask_threshold
        )

        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        evidence.log_execution_step(
            tool_name="get_orderbook_depth",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"{pair} bid_depth={bid_depth_2pct:.2f} ask_depth={ask_depth_2pct:.2f}",
        )

        summary = (
            f"買方 ±2% 深度 {bid_depth_2pct:.2f} {symbol_upper} / "
            f"賣方 ±2% 深度 {ask_depth_2pct:.2f} {symbol_upper}"
        )

        return {
            "raw": data,
            "source": source_url,
            "content_reference": {
                "endpoint": "https://api.binance.com/api/v3/depth",
                "symbol": symbol_upper,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "bid_depth_2pct": bid_depth_2pct,
                "ask_depth_2pct": ask_depth_2pct,
                "depth_limit": 1000,
                "fetched_at": fetched_at,
                "elapsed_ms": elapsed_ms,
            },
            "summary": summary,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="get_orderbook_depth",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[get_orderbook_depth] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def get_market_dominance(related_claim):
    """取得各主要幣種的市值佔比（dominance）。"""
    from config import COINGECKO_API_KEY

    source_url = "https://api.coingecko.com/api/v3/global"
    start_time = time.time()

    try:
        headers = {"User-Agent": "HoyabitAgent/1.0"}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

        resp = requests.get(source_url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        market_cap_pct = data.get("data", {}).get("market_cap_percentage", {})
        total_market_cap = data.get("data", {}).get("total_market_cap", {}).get("usd", 0)

        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # Summary
        btc_dom = market_cap_pct.get("btc", 0)
        eth_dom = market_cap_pct.get("eth", 0)
        summary = f"BTC dominance {btc_dom:.1f}%, ETH dominance {eth_dom:.1f}%, 總市值 ${total_market_cap/1e12:.2f}T"

        content_reference = {
            "endpoint": source_url,
            "dominance": market_cap_pct,
            "total_market_cap_usd": total_market_cap,
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
        }

        evidence.log_execution_step("get_market_dominance", "success", elapsed_ms, note=summary[:100])

        return {
            "raw": data,
            "source": source_url,
            "content_reference": content_reference,
            "summary": summary,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step("get_market_dominance", "error", elapsed_ms, note=str(e))
        return {"error": f"[get_market_dominance] {type(e).__name__}: {str(e)}", "source": source_url, "content_reference": {}}
