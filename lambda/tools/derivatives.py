"""
derivatives.py — 衍生品市場資料工具

資料來源：Hyperliquid（主力，免鑰）/ Binance Futures（備援+散戶指標）/ Deribit（僅BTC/ETH，期權波動率）

設計考量：
- 資金費率極端值 = 市場擁擠方向，是短期反轉的前導指標
- OI 急增 + 價格滯漲 = 槓桿堆積，清算風險升高
- DVOL vs 已實現波動率價差 = 市場買保險程度（恐慌溢價）
- 單一入口函式 get_derivatives() 依 source 參數內部分派，與 onchain.py 模式一致
- 所有 HTTP 呼叫設 30 秒 timeout，失敗回傳 error dict，絕不拋出未處理例外
"""

import time
from datetime import datetime, timezone

import requests

import evidence


# ---- HTTP 請求統一配置 ----
_TIMEOUT = 30
_HEADERS = {"User-Agent": "HoyabitAgent/1.0"}

# ---- Hyperliquid API 設定 ----
_HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"

# ---- Binance Futures API 設定 ----
_BINANCE_FUTURES_BASE = "https://fapi.binance.com"

# ---- Deribit API 設定 ----
_DERIBIT_BASE = "https://www.deribit.com/api/v2"


def get_derivatives(symbol, source, metrics, related_claim):
    """取得衍生品市場資料（資金費率、OI、清算、DVOL、多空比等）。

    依 source 參數分派到不同來源的 fetcher，各來源支援不同指標。
    所有例外在最外層捕獲，保證不向外拋出。

    Args:
        symbol: 幣種代碼（BTC, ETH, SOL, BNB, XRP）
        source: 資料來源，可選 "hyperliquid" | "binance_futures" | "deribit"
        metrics: 要取得的指標列表
        related_claim: Agent 說明取數目的（必填）

    Returns:
        Contract C1 dict or error dict
    """
    # 功能：依 source 參數分派到對應的 fetcher
    # 步驟：
    #   1. 標準化 source 為小寫
    #   2. match-case 分派
    #   3. 不認識的 source 直接回傳 error
    # 回傳：對應 fetcher 的 Contract C1 dict 或 error dict

    source_lower = source.lower().strip() if source else ""

    if source_lower == "hyperliquid":
        return _fetch_hyperliquid(symbol, metrics)
    elif source_lower == "binance_futures":
        return _fetch_binance_futures(symbol, metrics)
    elif source_lower == "deribit":
        return _fetch_deribit(symbol, metrics)
    else:
        return {"error": f"[get_derivatives] Unsupported derivatives source: {source}"}


def _fetch_hyperliquid(symbol, metrics):
    """從 Hyperliquid 取得衍生品資料（資金費率、OI、mark price）。

    Hyperliquid 免鑰、無硬限制 rate limit，回傳所有上架幣種的即時衍生品數據。
    資金費率為每小時費率，乘以 8 得到 8h 費率（業界慣用顯示方式）。
    """
    # 功能：從 Hyperliquid API 取得指定 symbol 的衍生品即時數據
    # 步驟：
    #   1. POST metaAndAssetCtxs 取得全部幣種的 meta + assetCtxs
    #   2. 從 meta.universe 中找到 symbol 對應的 index
    #   3. 從 assetCtxs[index] 提取 funding、openInterest、markPx
    #   4. 計算 8h 資金費率、判斷方向（多頭付費/空頭付費/中性）
    #   5. 組裝 Contract C1 回傳格式
    # 回傳：Contract C1 dict（raw, source, content_reference, summary）

    start_time = time.time()

    try:
        # 步驟 1：呼叫 Hyperliquid API
        payload = {"type": "metaAndAssetCtxs"}
        resp = requests.post(
            _HYPERLIQUID_URL,
            json=payload,
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        # 步驟 2：解析回傳結構 [meta_dict, [assetCtx, ...]]
        meta = data[0]
        asset_ctxs = data[1]
        universe = meta.get("universe", [])

        # 在 universe 中找 symbol 對應的 index
        symbol_upper = symbol.upper().strip()
        target_index = None
        for i, coin_info in enumerate(universe):
            if coin_info.get("name", "").upper() == symbol_upper:
                target_index = i
                break

        if target_index is None:
            elapsed_ms = int((time.time() - start_time) * 1000)
            evidence.log_execution_step(
                "get_derivatives", "error", elapsed_ms,
                note=f"Symbol {symbol_upper} not found in Hyperliquid universe"
            )
            return {
                "error": f"[_fetch_hyperliquid] Symbol '{symbol_upper}' not found in Hyperliquid listed coins",
                "source": _HYPERLIQUID_URL,
                "content_reference": {},
                "fallback_suggestion": "binance_futures",
            }

        # 步驟 3：提取目標幣種的衍生品數據
        ctx = asset_ctxs[target_index]
        funding_rate_hourly = float(ctx.get("funding", 0))
        open_interest = float(ctx.get("openInterest", 0))
        mark_price = float(ctx.get("markPx", 0))

        # 步驟 4：計算 8h 資金費率與方向判斷
        funding_rate_8h = funding_rate_hourly * 8
        open_interest_usd = open_interest * mark_price

        # 方向判斷：正費率=多頭付費（做多成本高），負費率=空頭付費，接近零=中性
        if funding_rate_8h > 0.0001:
            direction = "多頭付費"
        elif funding_rate_8h < -0.0001:
            direction = "空頭付費"
        else:
            direction = "中性"

        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # 步驟 5：組裝 Contract C1 回傳
        funding_pct = funding_rate_8h * 100

        # OI 金額格式化
        if open_interest_usd >= 1_000_000_000:
            oi_display = f"${open_interest_usd / 1_000_000_000:.2f}B"
        elif open_interest_usd >= 1_000_000:
            oi_display = f"${open_interest_usd / 1_000_000:.1f}M"
        else:
            oi_display = f"${open_interest_usd:,.0f}"

        summary = f"資金費率 {funding_pct:+.4f}%/8h，{direction}，OI {oi_display}"

        content_reference = {
            "endpoints_called": [_HYPERLIQUID_URL],
            "query_params": {"type": "metaAndAssetCtxs"},
            "symbol": symbol_upper,
            "source_name": "Hyperliquid",
            "funding_rate": funding_rate_8h,
            "open_interest_usd": open_interest_usd,
            "mark_price": mark_price,
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
        }

        result = {
            "raw": {
                "meta_universe_entry": universe[target_index],
                "asset_ctx": ctx,
            },
            "source": _HYPERLIQUID_URL,
            "content_reference": content_reference,
            "summary": summary,
        }

        # 記錄執行步驟
        evidence.log_execution_step(
            "get_derivatives", "success", elapsed_ms,
            note=f"Hyperliquid {symbol_upper}: funding={funding_pct:+.4f}%/8h, OI={oi_display}"
        )

        return result

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            "get_derivatives", "error", elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}"
        )
        return {
            "error": f"[_fetch_hyperliquid] {type(e).__name__}: {str(e)}",
            "source": _HYPERLIQUID_URL,
            "content_reference": {},
            "fallback_suggestion": "binance_futures",
        }


def _fetch_binance_futures(symbol, metrics):
    """從 Binance Futures 取得衍生品資料（資金費率、OI、大戶多空比、吃單買賣比）。

    Binance Futures API 免鑰，所有 endpoint 為 GET 請求。
    依 metrics 參數決定呼叫哪些 endpoint，個別 endpoint 失敗不影響其他指標取得。
    """
    # 功能：從 Binance Futures API 取得指定 symbol 的衍生品即時數據
    # 步驟：
    #   1. 依 metrics 列表逐一呼叫對應 endpoint
    #   2. 個別 metric 失敗時記錄錯誤但繼續
    #   3. 組裝 Contract C1 回傳格式（含所有成功取得的指標）
    # 回傳：Contract C1 dict（raw, source, content_reference, summary）

    start_time = time.time()
    symbol_upper = symbol.upper().strip()
    pair = f"{symbol_upper}USDT"

    # 收集各指標結果
    raw_data = {}
    results = {}
    errors = []
    endpoints_called = []

    try:
        # ---- 資金費率 (premiumIndex) ----
        if "funding_rate" in metrics:
            try:
                url = f"{_BINANCE_FUTURES_BASE}/fapi/v1/premiumIndex"
                params = {"symbol": pair}
                resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                endpoints_called.append(url)
                raw_data["premiumIndex"] = data

                funding_rate = float(data.get("lastFundingRate", 0))
                mark_price = float(data.get("markPrice", 0))
                index_price = float(data.get("indexPrice", 0))
                next_funding_time = data.get("nextFundingTime", 0)

                results["funding_rate"] = funding_rate
                results["mark_price"] = mark_price
                results["index_price"] = index_price
                results["next_funding_time"] = next_funding_time
            except Exception as e:
                errors.append(f"funding_rate: {type(e).__name__}: {str(e)}")

        # ---- 未平倉量 (openInterest) ----
        if "open_interest" in metrics:
            try:
                url = f"{_BINANCE_FUTURES_BASE}/fapi/v1/openInterest"
                params = {"symbol": pair}
                resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                endpoints_called.append(url)
                raw_data["openInterest"] = data

                open_interest_qty = float(data.get("openInterest", 0))
                results["open_interest_qty"] = open_interest_qty
            except Exception as e:
                errors.append(f"open_interest: {type(e).__name__}: {str(e)}")

        # ---- 大戶多空比 (topLongShortPositionRatio) ----
        if "long_short_ratio" in metrics:
            try:
                url = f"{_BINANCE_FUTURES_BASE}/futures/data/topLongShortPositionRatio"
                params = {"symbol": pair, "period": "5m", "limit": 1}
                resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                endpoints_called.append(url)
                raw_data["topLongShortPositionRatio"] = data

                if data and len(data) > 0:
                    entry = data[0]
                    long_short_ratio = float(entry.get("longShortRatio", 0))
                    long_account = float(entry.get("longAccount", 0))
                    short_account = float(entry.get("shortAccount", 0))
                    results["long_short_ratio"] = long_short_ratio
                    results["long_account"] = long_account
                    results["short_account"] = short_account
            except Exception as e:
                errors.append(f"long_short_ratio: {type(e).__name__}: {str(e)}")

        # ---- 吃單買賣比 (takerlongshortRatio) ----
        if "taker_buy_sell_ratio" in metrics:
            try:
                url = f"{_BINANCE_FUTURES_BASE}/futures/data/takerlongshortRatio"
                params = {"symbol": pair, "period": "5m", "limit": 1}
                resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                endpoints_called.append(url)
                raw_data["takerlongshortRatio"] = data

                if data and len(data) > 0:
                    entry = data[0]
                    buy_sell_ratio = float(entry.get("buySellRatio", 0))
                    buy_vol = float(entry.get("buyVol", 0))
                    sell_vol = float(entry.get("sellVol", 0))
                    results["taker_buy_sell_ratio"] = buy_sell_ratio
                    results["taker_buy_vol"] = buy_vol
                    results["taker_sell_vol"] = sell_vol
            except Exception as e:
                errors.append(f"taker_buy_sell_ratio: {type(e).__name__}: {str(e)}")

        # ---- 組裝結果 ----
        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # 若所有 metric 都失敗，回傳 error dict
        if not results:
            error_msg = "; ".join(errors) if errors else "No metrics retrieved"
            evidence.log_execution_step(
                "get_derivatives", "error", elapsed_ms,
                note=f"Binance Futures {symbol_upper}: all metrics failed — {error_msg}"
            )
            return {
                "error": f"[_fetch_binance_futures] All requested metrics failed: {error_msg}",
                "source": _BINANCE_FUTURES_BASE,
                "content_reference": {},
            }

        # 組裝 summary
        summary_parts = []

        if "funding_rate" in results:
            funding_pct = results["funding_rate"] * 100
            if results["funding_rate"] > 0.0001:
                direction = "多頭付費"
            elif results["funding_rate"] < -0.0001:
                direction = "空頭付費"
            else:
                direction = "中性"
            summary_parts.append(f"資金費率 {funding_pct:+.4f}%/8h（{direction}）")

        if "open_interest_qty" in results:
            oi_qty = results["open_interest_qty"]
            # 若有 mark_price，計算 USD 價值
            if "mark_price" in results and results["mark_price"] > 0:
                oi_usd = oi_qty * results["mark_price"]
                if oi_usd >= 1_000_000_000:
                    oi_display = f"${oi_usd / 1_000_000_000:.2f}B"
                elif oi_usd >= 1_000_000:
                    oi_display = f"${oi_usd / 1_000_000:.1f}M"
                else:
                    oi_display = f"${oi_usd:,.0f}"
                summary_parts.append(f"OI {oi_display}")
            else:
                summary_parts.append(f"OI {oi_qty:.2f} 合約")

        if "long_short_ratio" in results:
            summary_parts.append(f"大戶多空比 {results['long_short_ratio']:.4f}")

        if "taker_buy_sell_ratio" in results:
            summary_parts.append(f"吃單比 {results['taker_buy_sell_ratio']:.4f}")

        summary = f"Binance Futures {symbol_upper}: " + ", ".join(summary_parts)

        # 若有部分失敗，附註
        if errors:
            summary += f"（部分指標失敗: {'; '.join(errors)}）"

        # content_reference
        content_reference = {
            "endpoints_called": endpoints_called,
            "symbol": symbol_upper,
            "source_name": "Binance Futures",
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
        }
        # 將所有成功取得的指標值加入 content_reference
        content_reference.update(results)

        result = {
            "raw": raw_data,
            "source": _BINANCE_FUTURES_BASE,
            "content_reference": content_reference,
            "summary": summary,
        }

        # 記錄執行步驟
        evidence.log_execution_step(
            "get_derivatives", "success", elapsed_ms,
            note=f"Binance Futures {symbol_upper}: {', '.join(summary_parts)}"
        )

        return result

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            "get_derivatives", "error", elapsed_ms,
            note=f"Binance Futures {symbol_upper}: {type(e).__name__}: {str(e)}"
        )
        return {
            "error": f"[_fetch_binance_futures] {type(e).__name__}: {str(e)}",
            "source": _BINANCE_FUTURES_BASE,
            "content_reference": {},
        }


def _fetch_deribit(symbol, metrics):
    """從 Deribit 取得期權衍生品資料（DVOL 隱含波動率、期權 OI、Put/Call 比率）。

    Deribit 免鑰公開 API，僅支援 BTC 與 ETH。
    DVOL 為 Deribit 自編的隱含波動率指數，類似 VIX。
    Put/Call 比率由遍歷所有期權 instrument 的 OI 計算得出。
    """
    # 功能：從 Deribit API 取得指定 symbol 的期權衍生品數據
    # 步驟：
    #   1. 驗證 symbol 必須為 BTC 或 ETH
    #   2. 依 metrics 取得 DVOL / 期權 OI / Put-Call 比率
    #   3. 組裝 Contract C1 回傳格式
    # 回傳：Contract C1 dict（raw, source, content_reference, summary）

    start_time = time.time()
    symbol_upper = symbol.upper().strip()

    # 步驟 1：驗證 symbol（Deribit 僅支援 BTC 與 ETH）
    if symbol_upper not in ("BTC", "ETH"):
        return {"error": f"[_fetch_deribit] Deribit 僅支援 BTC 與 ETH，不支援 {symbol_upper}"}

    try:
        currency = symbol_upper  # Deribit 使用 BTC / ETH 作為 currency 參數
        raw_data = {}
        results = {}
        endpoints_called = []

        # ---- DVOL 隱含波動率指數 ----
        if "dvol" in metrics:
            try:
                now_ms = int(time.time() * 1000)
                start_ms = now_ms - 24 * 3600 * 1000  # 過去 24 小時

                url = f"{_DERIBIT_BASE}/public/get_volatility_index_data"
                params = {
                    "currency": currency,
                    "start_timestamp": start_ms,
                    "end_timestamp": now_ms,
                    "resolution": 3600,
                }
                resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                endpoints_called.append(url)
                raw_data["volatility_index_data"] = data

                # result.data 為 candle 陣列 [timestamp, open, high, low, close]
                candles = data.get("result", {}).get("data", [])
                if candles:
                    # 取最後一根 candle 的 close 作為當前 DVOL
                    last_candle = candles[-1]
                    dvol_value = float(last_candle[4])  # close
                    results["dvol"] = dvol_value
                else:
                    results["dvol"] = None
            except Exception as e:
                results["dvol_error"] = f"{type(e).__name__}: {str(e)}"

        # ---- 期權 OI + Put/Call 比率 ----
        if "options_oi" in metrics or "put_call_ratio" in metrics:
            try:
                url = f"{_DERIBIT_BASE}/public/get_book_summary_by_currency"
                params = {"currency": currency, "kind": "option"}
                resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                endpoints_called.append(url)
                raw_data["book_summary_by_currency"] = data

                # 遍歷所有 option instrument，分類 Put/Call 並加總 OI
                instruments = data.get("result", [])
                total_put_oi = 0.0
                total_call_oi = 0.0

                for inst in instruments:
                    instrument_name = inst.get("instrument_name", "")
                    oi = float(inst.get("open_interest", 0))

                    if "-P" in instrument_name:
                        total_put_oi += oi
                    elif "-C" in instrument_name:
                        total_call_oi += oi

                total_options_oi = total_put_oi + total_call_oi
                results["options_oi"] = total_options_oi
                results["put_oi"] = total_put_oi
                results["call_oi"] = total_call_oi

                # Put/Call 比率
                if total_call_oi > 0:
                    put_call_ratio = total_put_oi / total_call_oi
                else:
                    put_call_ratio = 0.0
                results["put_call_ratio"] = put_call_ratio

            except Exception as e:
                results["options_error"] = f"{type(e).__name__}: {str(e)}"

        # ---- 組裝結果 ----
        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # 檢查是否有任何成功的指標
        has_dvol = "dvol" in results and results["dvol"] is not None
        has_oi = "options_oi" in results
        has_pcr = "put_call_ratio" in results

        if not has_dvol and not has_oi and not has_pcr:
            # 所有指標都失敗
            error_details = []
            if "dvol_error" in results:
                error_details.append(f"dvol: {results['dvol_error']}")
            if "options_error" in results:
                error_details.append(f"options: {results['options_error']}")
            error_msg = "; ".join(error_details) if error_details else "No metrics retrieved"

            evidence.log_execution_step(
                "get_derivatives", "error", elapsed_ms,
                note=f"Deribit {symbol_upper}: all metrics failed — {error_msg}"
            )
            return {
                "error": f"[_fetch_deribit] All requested metrics failed: {error_msg}",
                "source": _DERIBIT_BASE,
                "content_reference": {},
            }

        # 組裝 summary
        summary_parts = []
        if has_dvol:
            summary_parts.append(f"DVOL {results['dvol']:.1f}%")
        if has_oi:
            oi_val = results["options_oi"]
            if oi_val >= 1_000_000:
                oi_display = f"{oi_val / 1_000_000:.1f}M"
            elif oi_val >= 1_000:
                oi_display = f"{oi_val / 1_000:.1f}K"
            else:
                oi_display = f"{oi_val:.1f}"
            summary_parts.append(f"期權OI {oi_display}")
        if has_pcr:
            summary_parts.append(f"Put/Call比率 {results['put_call_ratio']:.4f}")

        summary = f"Deribit {symbol_upper}: " + ", ".join(summary_parts)

        # content_reference
        content_reference = {
            "endpoints_called": endpoints_called,
            "symbol": symbol_upper,
            "source_name": "Deribit",
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
        }
        if has_dvol:
            content_reference["dvol"] = results["dvol"]
        if has_oi:
            content_reference["options_oi"] = results["options_oi"]
            content_reference["put_oi"] = results["put_oi"]
            content_reference["call_oi"] = results["call_oi"]
        if has_pcr:
            content_reference["put_call_ratio"] = results["put_call_ratio"]

        result = {
            "raw": raw_data,
            "source": _DERIBIT_BASE,
            "content_reference": content_reference,
            "summary": summary,
        }

        evidence.log_execution_step(
            "get_derivatives", "success", elapsed_ms,
            note=f"Deribit {symbol_upper}: {', '.join(summary_parts)}"
        )

        return result

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            "get_derivatives", "error", elapsed_ms,
            note=f"Deribit {symbol_upper}: {type(e).__name__}: {str(e)}"
        )
        return {
            "error": f"[_fetch_deribit] {type(e).__name__}: {str(e)}",
            "source": _DERIBIT_BASE,
            "content_reference": {},
        }
