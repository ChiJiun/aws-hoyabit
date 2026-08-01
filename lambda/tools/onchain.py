"""
onchain.py — 鏈上資料工具

這是唯一需要依幣種分派到不同來源的工具，因為五個幣種是五條獨立的區塊鏈，
各自有自己的查詢介面。其他工具（價格、新聞、情緒）都是共用同一來源、
只換查詢參數。
"""

import time
from datetime import datetime, timezone

import requests

import config
import evidence
from tools.quality import make_anomaly_flag

# mempool.space 基本設定
_MEMPOOL_BASE = "https://mempool.space/api"
_HEADERS = {"User-Agent": "HoyabitAgent/1.0"}
_TIMEOUT = 30

# 支援的 BTC 鏈上指標
_SUPPORTED_BTC_METRICS = {"tx_count", "mempool_size", "fees", "hashrate", "difficulty_adjustment"}


def _detect_activity_deviation(result, symbol):
    """A9: 檢測鏈上活躍度偏離 30 日均值 ±30%。

    從各鏈回傳的 raw 結構中嘗試提取交易量/活躍度指標，
    若有 current vs baseline 的比較資訊則計算偏離百分比。
    僅在資料充分時產生 flag，資料不足則靜默略過（寧缺勿濫）。
    """
    flags = []
    thresholds = getattr(config, "ANOMALY_THRESHOLDS", {})
    deviation_pct = thresholds.get("onchain_activity_deviation_pct", 30.0)

    raw = result.get("raw", {})
    if not isinstance(raw, dict):
        return flags

    # 各鏈的活躍度指標提取策略
    current_value = None
    baseline_value = None
    metric_name = "tx_count"

    if symbol == "BTC":
        # BTC: raw["tx_count"]["avg_tx_per_block"] vs 歷史平均（若有）
        tx_data = raw.get("tx_count", {})
        if isinstance(tx_data, dict) and "avg_tx_per_block" in tx_data:
            current_value = tx_data.get("avg_tx_per_block")
            # mempool 沒有提供 30 日基準，暫無法計算偏離
    elif symbol in ("ETH", "BNB"):
        # EVM: raw["tx_count"] 可能有 recent_total_transactions
        tx_data = raw.get("tx_count", {})
        if isinstance(tx_data, dict):
            current_value = tx_data.get("recent_total_transactions")
            baseline_value = tx_data.get("baseline_daily_avg")
            metric_name = "daily_transactions"
    elif symbol == "SOL":
        tx_data = raw.get("tx_count", {})
        if isinstance(tx_data, dict):
            current_value = tx_data.get("recent_total_transactions")
            baseline_value = tx_data.get("baseline_daily_avg")
            metric_name = "daily_transactions"
    elif symbol == "XRP":
        tx_data = raw.get("tx_count", {})
        if isinstance(tx_data, dict):
            current_value = tx_data.get("recent_total_transactions")
            baseline_value = tx_data.get("baseline_daily_avg")
            metric_name = "daily_transactions"

    # 計算偏離
    if current_value and baseline_value and baseline_value > 0:
        deviation = ((current_value - baseline_value) / baseline_value) * 100
        if abs(deviation) >= deviation_pct:
            direction = "bullish" if deviation > 0 else "bearish"
            flags.append(make_anomaly_flag(
                signal_id="A9_onchain_activity_deviation",
                name="鏈上活躍度偏離",
                severity="significant" if abs(deviation) >= 50.0 else "notable",
                direction=direction,
                value=round(deviation, 1),
                unit="% vs 30d avg",
                threshold=f"|deviation| ≥ {deviation_pct}%",
                window="vs 30d baseline",
                as_of=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                message=f"{symbol} 鏈上{metric_name}偏離 30 日均值 {deviation:+.1f}%"
                        f"（當前 {current_value:,.0f} vs 基準 {baseline_value:,.0f}）",
            ))

    return flags


def get_onchain(symbol, metrics, lookback_days, related_claim):
    """取得指定幣種的鏈上活躍度指標。

    依 symbol 分派到對應的鏈上來源函式，取得指標後統一格式回傳。
      BTC → fetch_btc_onchain()      mempool.space
      ETH → fetch_evm_onchain()      Etherscan API V2
      BNB → fetch_evm_onchain()      Blockscout
      SOL → fetch_sol_onchain()      Helius
      XRP → fetch_xrp_onchain()      XRPL 公開節點

    Args:
        symbol: 幣種代碼（BTC, ETH, BNB, SOL, XRP）
        metrics: 要取得的指標列表
        lookback_days: 回溯天數
        related_claim: Agent 框架所需參數（本函式不使用）

    Returns:
        統一格式 dict：成功時含 raw/source/content_reference/summary，
        失敗時含 error/source/content_reference。
    """
    try:
        sym = symbol.upper() if symbol else ""

        match sym:
            case "BTC":
                result = fetch_btc_onchain(metrics, lookback_days)
            case "ETH":
                result = fetch_evm_onchain("ethereum", metrics, lookback_days)
            case "BNB":
                result = fetch_evm_onchain("bsc", metrics, lookback_days)
            case "SOL":
                result = fetch_sol_onchain(metrics, lookback_days)
            case "XRP":
                result = fetch_xrp_onchain(metrics, lookback_days)
            case _:
                return {
                    "error": f"[get_onchain] Unsupported symbol: {symbol}",
                    "source": "",
                    "content_reference": {},
                }

        # --- A9 異常偵測：鏈上活躍度偏離 ---
        if "error" not in result:
            a9_flags = _detect_activity_deviation(result, sym)
            if a9_flags:
                existing = result.get("anomaly_flags", [])
                result["anomaly_flags"] = existing + a9_flags

        return result
    except Exception as e:
        return {
            "error": f"[get_onchain] {type(e).__name__}: {str(e)}",
            "source": "",
            "content_reference": {},
        }


def fetch_btc_onchain(metrics, lookback_days):
    """從 mempool.space 取得比特幣鏈上資料（免 API 金鑰）。

    支援指標：tx_count, mempool_size, fees, hashrate, difficulty_adjustment
    若 metrics 為空或 None，則取得所有支援的指標。

    Args:
        metrics: 要取得的指標列表，例如 ["tx_count", "fees"]
        lookback_days: 回溯天數（用於 hashrate 時間區間）

    Returns:
        統一格式 dict：成功時含 raw/source/content_reference/summary，
        失敗時含 error/source/content_reference。
    """
    source_url = f"{_MEMPOOL_BASE} (mempool.space public API)"
    start_time = time.time()
    endpoints_called = []

    try:
        # 決定要查詢哪些指標
        if not metrics:
            requested_metrics = _SUPPORTED_BTC_METRICS.copy()
        else:
            if isinstance(metrics, str):
                metrics = [metrics]
            requested_metrics = set(metrics) & _SUPPORTED_BTC_METRICS
            if not requested_metrics:
                # 如果傳入的 metrics 全部不支援，預設取所有
                requested_metrics = _SUPPORTED_BTC_METRICS.copy()

        raw_data = {}

        # --- tx_count: 從最近的區塊取得交易數量 ---
        if "tx_count" in requested_metrics:
            url = f"{_MEMPOOL_BASE}/blocks"
            endpoints_called.append(url)
            resp = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            blocks = resp.json()
            # 取最近 10 個區塊的 tx_count
            block_tx_counts = []
            for block in blocks[:10]:
                block_tx_counts.append({
                    "height": block.get("height"),
                    "tx_count": block.get("tx_count", 0),
                    "timestamp": block.get("timestamp"),
                })
            total_tx = sum(b["tx_count"] for b in block_tx_counts)
            avg_tx = total_tx / len(block_tx_counts) if block_tx_counts else 0
            raw_data["tx_count"] = {
                "recent_blocks": block_tx_counts,
                "total_tx_in_recent_blocks": total_tx,
                "avg_tx_per_block": round(avg_tx, 1),
            }

        # --- mempool_size: 目前 mempool 狀態 ---
        if "mempool_size" in requested_metrics:
            url = f"{_MEMPOOL_BASE}/mempool"
            endpoints_called.append(url)
            resp = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            mempool_data = resp.json()
            raw_data["mempool_size"] = {
                "count": mempool_data.get("count", 0),
                "vsize": mempool_data.get("vsize", 0),
                "total_fee": mempool_data.get("total_fee", 0),
            }

        # --- fees: 建議費率 ---
        if "fees" in requested_metrics:
            url = f"{_MEMPOOL_BASE}/v1/fees/recommended"
            endpoints_called.append(url)
            resp = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            fees_data = resp.json()
            raw_data["fees"] = {
                "fastest_fee": fees_data.get("fastestFee"),
                "half_hour_fee": fees_data.get("halfHourFee"),
                "hour_fee": fees_data.get("hourFee"),
                "economy_fee": fees_data.get("economyFee"),
                "minimum_fee": fees_data.get("minimumFee"),
            }

        # --- hashrate: 網路算力 ---
        if "hashrate" in requested_metrics:
            # 使用 lookback_days 決定時間區間，最短 1 個月
            if lookback_days and lookback_days <= 30:
                time_period = "1m"
            elif lookback_days and lookback_days <= 90:
                time_period = "3m"
            elif lookback_days and lookback_days <= 180:
                time_period = "6m"
            else:
                time_period = "1m"
            url = f"{_MEMPOOL_BASE}/v1/mining/hashrate/{time_period}"
            endpoints_called.append(url)
            resp = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            hashrate_data = resp.json()
            # 取最近的 hashrate 資料點
            current_hashrate = hashrate_data.get("currentHashrate", 0)
            current_difficulty = hashrate_data.get("currentDifficulty", 0)
            hashrate_entries = hashrate_data.get("hashrates", [])
            recent_hashrates = hashrate_entries[-5:] if hashrate_entries else []
            raw_data["hashrate"] = {
                "current_hashrate": current_hashrate,
                "current_difficulty": current_difficulty,
                "recent_data_points": recent_hashrates,
                "time_period": time_period,
            }

        # --- difficulty_adjustment: 難度調整資訊 ---
        if "difficulty_adjustment" in requested_metrics:
            url = f"{_MEMPOOL_BASE}/v1/difficulty-adjustment"
            endpoints_called.append(url)
            resp = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            diff_data = resp.json()
            raw_data["difficulty_adjustment"] = {
                "progress_percent": diff_data.get("progressPercent"),
                "difficulty_change": diff_data.get("difficultyChange"),
                "estimated_retarget_date": diff_data.get("estimatedRetargetDate"),
                "remaining_blocks": diff_data.get("remainingBlocks"),
                "remaining_time": diff_data.get("remainingTime"),
                "previous_retarget": diff_data.get("previousRetarget"),
            }

        # --- 組裝 content_reference ---
        content_reference = {
            "endpoints_called": endpoints_called,
            "metrics_retrieved": list(raw_data.keys()),
            "data_time_range": f"lookback_days={lookback_days}",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # --- 組裝 summary ---
        summary_parts = [f"BTC 鏈上資料（來源：mempool.space）："]

        if "tx_count" in raw_data:
            avg = raw_data["tx_count"]["avg_tx_per_block"]
            total = raw_data["tx_count"]["total_tx_in_recent_blocks"]
            summary_parts.append(f"近 10 區塊平均交易數 {avg}，合計 {total} 筆")

        if "mempool_size" in raw_data:
            count = raw_data["mempool_size"]["count"]
            vsize_mb = raw_data["mempool_size"]["vsize"] / (1024 * 1024)
            summary_parts.append(f"Mempool 待確認交易 {count} 筆（{vsize_mb:.1f} MvB）")

        if "fees" in raw_data:
            fastest = raw_data["fees"]["fastest_fee"]
            hour = raw_data["fees"]["hour_fee"]
            economy = raw_data["fees"]["economy_fee"]
            summary_parts.append(f"費率：最快 {fastest} sat/vB、一小時 {hour}、經濟 {economy}")

        if "hashrate" in raw_data:
            hr = raw_data["hashrate"]["current_hashrate"]
            # 轉換為 EH/s 顯示
            if hr and hr > 0:
                hr_eh = hr / 1e18
                summary_parts.append(f"目前算力 {hr_eh:.1f} EH/s")

        if "difficulty_adjustment" in raw_data:
            progress = raw_data["difficulty_adjustment"]["progress_percent"]
            change = raw_data["difficulty_adjustment"]["difficulty_change"]
            if progress is not None and change is not None:
                summary_parts.append(
                    f"難度調整進度 {progress:.1f}%，預估變化 {change:+.2f}%"
                )

        summary = "；".join(summary_parts)

        # --- 記錄成功執行 ---
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="fetch_btc_onchain",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"BTC: retrieved {list(raw_data.keys())}",
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
            tool_name="fetch_btc_onchain",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"BTC: {type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[fetch_btc_onchain] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def fetch_evm_onchain(chain, metrics, lookback_days):
    """從 EVM 相容鏈的瀏覽器 API 取得鏈上資料。

    ETH 與 BNB 共用這個函式，因為 Etherscan V2 與 Blockscout 的 API 格式相容。
    chain="ethereum" → Etherscan API V2（需要 API 金鑰）
    chain="bsc"      → Blockscout（免金鑰）

    支援指標：tx_count, gas_price, eth_supply/bnb_supply, block_count
    若 metrics 為空或 None，則取得所有支援的指標。

    Args:
        chain: "ethereum" 或 "bsc"
        metrics: 要取得的指標列表，例如 ["tx_count", "gas_price"]
        lookback_days: 回溯天數（用於資料時間範圍描述）

    Returns:
        統一格式 dict：成功時含 raw/source/content_reference/summary，
        失敗時含 error/source/content_reference。
    """
    import config

    # --- 鏈別設定 ---
    _CHAIN_CONFIG = {
        "ethereum": {
            "base_url": "https://api.etherscan.io/v2/api",
            "chain_id": "1",
            "symbol": "ETH",
            "supply_action": "ethsupply",
            "requires_key": True,
            "source_name": "Etherscan API V2",
        },
        "bsc": {
            "base_url": "https://api.bscscan.com/api",
            "chain_id": "56",
            "symbol": "BNB",
            "supply_action": "bnbsupply",
            "requires_key": False,
            "source_name": "BscScan (Blockscout-compatible)",
        },
    }

    chain_cfg = _CHAIN_CONFIG.get(chain)
    if not chain_cfg:
        return {
            "error": f"[fetch_evm_onchain] Unsupported chain: {chain}",
            "source": "",
            "content_reference": {},
        }

    base_url = chain_cfg["base_url"]
    chain_id = chain_cfg["chain_id"]
    symbol = chain_cfg["symbol"]
    source_name = chain_cfg["source_name"]
    source_url = f"{base_url} ({source_name})"
    start_time = time.time()
    endpoints_called = []

    # --- 檢查 API 金鑰（僅 Etherscan 需要）---
    api_key = config.ETHERSCAN_API_KEY if chain_cfg["requires_key"] else None
    if chain_cfg["requires_key"] and not api_key:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="fetch_evm_onchain",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"{symbol}: ETHERSCAN_API_KEY not configured",
        )
        return {
            "error": f"[fetch_evm_onchain] ETHERSCAN_API_KEY 未設定，無法查詢 {symbol} 鏈上資料",
            "source": source_url,
            "content_reference": {},
        }

    # --- 支援的指標 ---
    _SUPPORTED_METRICS = {"tx_count", "gas_price", "supply", "block_count"}

    try:
        # 決定要查詢哪些指標
        if not metrics:
            requested_metrics = _SUPPORTED_METRICS.copy()
        else:
            if isinstance(metrics, str):
                metrics = [metrics]
            # 將 eth_supply / bnb_supply 正規化為 "supply"
            normalized = set()
            for m in metrics:
                if m in ("eth_supply", "bnb_supply"):
                    normalized.add("supply")
                else:
                    normalized.add(m)
            requested_metrics = normalized & _SUPPORTED_METRICS
            if not requested_metrics:
                requested_metrics = _SUPPORTED_METRICS.copy()

        raw_data = {}
        query_params_log = []

        def _build_params(module, action, extra=None):
            """建立共用的 API 查詢參數。"""
            params = {"module": module, "action": action}
            if chain == "ethereum":
                params["chainid"] = chain_id
            if api_key:
                params["apikey"] = api_key
            if extra:
                params.update(extra)
            return params

        def _call_api(params):
            """呼叫 API 並回傳 JSON，同時記錄 endpoint。"""
            endpoints_called.append(base_url)
            # 記錄查詢參數（遮蔽 API key）
            log_params = {k: v for k, v in params.items() if k != "apikey"}
            query_params_log.append(log_params)
            resp = requests.get(
                base_url, params=params, timeout=_TIMEOUT, headers=_HEADERS
            )
            resp.raise_for_status()
            return resp.json()

        # --- tx_count: 取得最近區塊的交易數量 ---
        if "tx_count" in requested_metrics:
            # 使用 proxy module 取得最新區塊號
            params = _build_params("proxy", "eth_blockNumber")
            data = _call_api(params)
            block_hex = data.get("result", "0x0")
            latest_block = int(block_hex, 16) if isinstance(block_hex, str) else 0

            # 取得最近區塊的交易數量（取 5 個區塊）
            block_tx_counts = []
            for offset in range(5):
                block_num = hex(latest_block - offset)
                params = _build_params(
                    "proxy", "eth_getBlockTransactionCountByNumber",
                    {"tag": block_num}
                )
                data = _call_api(params)
                tx_hex = data.get("result", "0x0")
                tx_count = int(tx_hex, 16) if isinstance(tx_hex, str) and tx_hex else 0
                block_tx_counts.append({
                    "block_number": latest_block - offset,
                    "tx_count": tx_count,
                })

            total_tx = sum(b["tx_count"] for b in block_tx_counts)
            avg_tx = total_tx / len(block_tx_counts) if block_tx_counts else 0
            raw_data["tx_count"] = {
                "recent_blocks": block_tx_counts,
                "total_tx_in_recent_blocks": total_tx,
                "avg_tx_per_block": round(avg_tx, 1),
                "latest_block": latest_block,
            }

        # --- gas_price: 目前 gas 價格 ---
        if "gas_price" in requested_metrics:
            params = _build_params("proxy", "eth_gasPrice")
            data = _call_api(params)
            gas_hex = data.get("result", "0x0")
            gas_wei = int(gas_hex, 16) if isinstance(gas_hex, str) and gas_hex else 0
            gas_gwei = gas_wei / 1e9
            raw_data["gas_price"] = {
                "gas_price_wei": gas_wei,
                "gas_price_gwei": round(gas_gwei, 2),
            }

        # --- supply: 代幣總供應量 ---
        if "supply" in requested_metrics:
            supply_action = chain_cfg["supply_action"]
            params = _build_params("stats", supply_action)
            data = _call_api(params)
            result = data.get("result", "0")
            # Etherscan 回傳的 supply 是 wei 單位
            try:
                supply_wei = int(result)
                supply_ether = supply_wei / 1e18
            except (ValueError, TypeError):
                supply_wei = 0
                supply_ether = 0.0
            raw_data["supply"] = {
                "total_supply_wei": supply_wei,
                "total_supply": round(supply_ether, 4),
                "unit": symbol,
            }

        # --- block_count: 每日區塊數量估算 ---
        if "block_count" in requested_metrics:
            # 使用最新區塊號和時間戳計算區塊速率
            params = _build_params("proxy", "eth_blockNumber")
            data = _call_api(params)
            block_hex = data.get("result", "0x0")
            current_block = int(block_hex, 16) if isinstance(block_hex, str) else 0

            # 估算每日區塊數（ETH ~12s/block ≈ 7200/day, BNB ~3s/block ≈ 28800/day）
            if chain == "ethereum":
                estimated_daily_blocks = 7200
                block_time_sec = 12
            else:
                estimated_daily_blocks = 28800
                block_time_sec = 3

            raw_data["block_count"] = {
                "current_block_number": current_block,
                "estimated_daily_blocks": estimated_daily_blocks,
                "avg_block_time_seconds": block_time_sec,
            }

        # --- 組裝 content_reference ---
        content_reference = {
            "endpoints_called": endpoints_called,
            "query_params": query_params_log,
            "metrics_retrieved": list(raw_data.keys()),
            "data_time_range": f"lookback_days={lookback_days}",
            "chain": chain,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # --- 組裝 summary ---
        summary_parts = [f"{symbol} 鏈上資料（來源：{source_name}）："]

        if "tx_count" in raw_data:
            avg = raw_data["tx_count"]["avg_tx_per_block"]
            total = raw_data["tx_count"]["total_tx_in_recent_blocks"]
            latest = raw_data["tx_count"]["latest_block"]
            summary_parts.append(
                f"近 5 區塊平均交易數 {avg}（合計 {total} 筆，最新區塊 #{latest}）"
            )

        if "gas_price" in raw_data:
            gwei = raw_data["gas_price"]["gas_price_gwei"]
            summary_parts.append(f"目前 Gas Price {gwei} Gwei")

        if "supply" in raw_data:
            supply = raw_data["supply"]["total_supply"]
            unit = raw_data["supply"]["unit"]
            # 以百萬為單位顯示
            supply_m = supply / 1e6
            summary_parts.append(f"總供應量 {supply_m:.2f}M {unit}")

        if "block_count" in raw_data:
            daily = raw_data["block_count"]["estimated_daily_blocks"]
            block_time = raw_data["block_count"]["avg_block_time_seconds"]
            current = raw_data["block_count"]["current_block_number"]
            summary_parts.append(
                f"目前區塊 #{current}，每日約 {daily} 區塊（{block_time}s/block）"
            )

        summary = "；".join(summary_parts)

        # --- 記錄成功執行 ---
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="fetch_evm_onchain",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"{symbol}: retrieved {list(raw_data.keys())}",
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
            tool_name="fetch_evm_onchain",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"{symbol}: {type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[fetch_evm_onchain] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def fetch_sol_onchain(metrics, lookback_days):
    """從 Helius 取得 Solana 鏈上資料（需 HELIUS_API_KEY）。

    使用 Helius 作為 Solana JSON-RPC 端點，呼叫標準 Solana RPC 方法。
    注意：不要用 Solscan 官方 API，該服務已改為付費方案。

    支援指標：tx_count, tps, slot_height, active_validators, supply, epoch_info
    若 metrics 為空或 None，則取得所有支援的指標。

    Args:
        metrics: 要取得的指標列表，例如 ["tps", "supply"]
        lookback_days: 回溯天數（用於資料時間範圍描述）

    Returns:
        統一格式 dict：成功時含 raw/source/content_reference/summary，
        失敗時含 error/source/content_reference。
    """
    import config

    _SUPPORTED_SOL_METRICS = {"tx_count", "tps", "slot_height", "active_validators", "supply", "epoch_info"}

    # --- 檢查 API 金鑰 ---
    api_key = config.HELIUS_API_KEY
    helius_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}" if api_key else ""
    source_url = "https://mainnet.helius-rpc.com (Helius Solana RPC)"
    start_time = time.time()

    if not api_key:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="fetch_sol_onchain",
            status="error",
            elapsed_ms=elapsed_ms,
            note="SOL: HELIUS_API_KEY not configured",
        )
        return {
            "error": "[fetch_sol_onchain] HELIUS_API_KEY 未設定，無法查詢 SOL 鏈上資料",
            "source": source_url,
            "content_reference": {},
        }

    endpoints_called = []

    try:
        # 決定要查詢哪些指標
        if not metrics:
            requested_metrics = _SUPPORTED_SOL_METRICS.copy()
        else:
            if isinstance(metrics, str):
                metrics = [metrics]
            requested_metrics = set(metrics) & _SUPPORTED_SOL_METRICS
            if not requested_metrics:
                requested_metrics = _SUPPORTED_SOL_METRICS.copy()

        raw_data = {}

        def _rpc_call(method, params=None):
            """呼叫 Solana JSON-RPC 方法。"""
            endpoints_called.append(f"helius-rpc/{method}")
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params or [],
            }
            resp = requests.post(
                helius_url,
                json=payload,
                timeout=_TIMEOUT,
                headers={**_HEADERS, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"RPC error: {data['error']}")
            return data.get("result")

        # --- tps / tx_count: 從 getRecentPerformanceSamples 取得 ---
        if "tps" in requested_metrics or "tx_count" in requested_metrics:
            # 取最近 10 個 performance samples（每個約 60 秒的時段）
            samples = _rpc_call("getRecentPerformanceSamples", [10])
            if samples:
                total_tx = sum(s.get("numTransactions", 0) for s in samples)
                total_seconds = sum(s.get("samplePeriodSecs", 60) for s in samples)
                avg_tps = total_tx / total_seconds if total_seconds > 0 else 0
                total_slots = sum(s.get("numSlots", 0) for s in samples)

                if "tps" in requested_metrics:
                    raw_data["tps"] = {
                        "avg_tps": round(avg_tps, 2),
                        "sample_count": len(samples),
                        "total_transactions": total_tx,
                        "total_seconds": total_seconds,
                    }
                if "tx_count" in requested_metrics:
                    raw_data["tx_count"] = {
                        "recent_total_transactions": total_tx,
                        "sample_period_seconds": total_seconds,
                        "total_slots_sampled": total_slots,
                    }

        # --- epoch_info / slot_height: 從 getEpochInfo 取得 ---
        if "epoch_info" in requested_metrics or "slot_height" in requested_metrics:
            epoch_info = _rpc_call("getEpochInfo")
            if epoch_info:
                current_slot = epoch_info.get("absoluteSlot", 0)
                epoch = epoch_info.get("epoch", 0)
                slot_index = epoch_info.get("slotIndex", 0)
                slots_in_epoch = epoch_info.get("slotsInEpoch", 0)
                epoch_progress = (slot_index / slots_in_epoch * 100) if slots_in_epoch > 0 else 0

                if "epoch_info" in requested_metrics:
                    raw_data["epoch_info"] = {
                        "epoch": epoch,
                        "slot_index": slot_index,
                        "slots_in_epoch": slots_in_epoch,
                        "epoch_progress_percent": round(epoch_progress, 2),
                        "absolute_slot": current_slot,
                        "transaction_count": epoch_info.get("transactionCount"),
                    }
                if "slot_height" in requested_metrics:
                    raw_data["slot_height"] = {
                        "absolute_slot": current_slot,
                        "block_height": epoch_info.get("blockHeight", 0),
                    }

        # --- active_validators: 從 getVoteAccounts 取得 ---
        if "active_validators" in requested_metrics:
            vote_accounts = _rpc_call("getVoteAccounts")
            if vote_accounts:
                current_validators = vote_accounts.get("current", [])
                delinquent_validators = vote_accounts.get("delinquent", [])
                active_count = len(current_validators)
                delinquent_count = len(delinquent_validators)
                total_active_stake = sum(
                    int(v.get("activatedStake", 0)) for v in current_validators
                )
                raw_data["active_validators"] = {
                    "active_count": active_count,
                    "delinquent_count": delinquent_count,
                    "total_validators": active_count + delinquent_count,
                    "total_active_stake_lamports": total_active_stake,
                    "total_active_stake_sol": round(total_active_stake / 1e9, 2),
                }

        # --- supply: 從 getSupply 取得 ---
        if "supply" in requested_metrics:
            supply_data = _rpc_call("getSupply")
            if supply_data:
                value = supply_data.get("value", {})
                total_lamports = value.get("total", 0)
                circulating_lamports = value.get("circulating", 0)
                non_circulating_lamports = value.get("nonCirculating", 0)
                raw_data["supply"] = {
                    "total_lamports": total_lamports,
                    "total_sol": round(total_lamports / 1e9, 4),
                    "circulating_lamports": circulating_lamports,
                    "circulating_sol": round(circulating_lamports / 1e9, 4),
                    "non_circulating_lamports": non_circulating_lamports,
                    "non_circulating_sol": round(non_circulating_lamports / 1e9, 4),
                }

        # --- 組裝 content_reference ---
        content_reference = {
            "endpoints_called": endpoints_called,
            "metrics_retrieved": list(raw_data.keys()),
            "data_time_range": f"lookback_days={lookback_days}",
            "rpc_base": "https://mainnet.helius-rpc.com",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # --- 組裝 summary ---
        summary_parts = ["SOL 鏈上資料（來源：Helius Solana RPC）："]

        if "tps" in raw_data:
            avg_tps = raw_data["tps"]["avg_tps"]
            summary_parts.append(f"平均 TPS {avg_tps}")

        if "tx_count" in raw_data:
            total_tx = raw_data["tx_count"]["recent_total_transactions"]
            period = raw_data["tx_count"]["sample_period_seconds"]
            summary_parts.append(f"近 {period} 秒交易量 {total_tx} 筆")

        if "epoch_info" in raw_data:
            epoch = raw_data["epoch_info"]["epoch"]
            progress = raw_data["epoch_info"]["epoch_progress_percent"]
            summary_parts.append(f"Epoch {epoch}（進度 {progress}%）")

        if "slot_height" in raw_data:
            slot = raw_data["slot_height"]["absolute_slot"]
            block_h = raw_data["slot_height"]["block_height"]
            summary_parts.append(f"Slot #{slot}，Block Height #{block_h}")

        if "active_validators" in raw_data:
            active = raw_data["active_validators"]["active_count"]
            stake_sol = raw_data["active_validators"]["total_active_stake_sol"]
            summary_parts.append(f"活躍驗證者 {active} 個，質押 {stake_sol:,.0f} SOL")

        if "supply" in raw_data:
            circulating = raw_data["supply"]["circulating_sol"]
            total = raw_data["supply"]["total_sol"]
            summary_parts.append(
                f"流通供應 {circulating:,.0f} SOL / 總供應 {total:,.0f} SOL"
            )

        summary = "；".join(summary_parts)

        # --- 記錄成功執行 ---
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="fetch_sol_onchain",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"SOL: retrieved {list(raw_data.keys())}",
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
            tool_name="fetch_sol_onchain",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"SOL: {type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[fetch_sol_onchain] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def fetch_xrp_onchain(metrics, lookback_days):
    """從 XRPL 公開節點取得 XRP 帳本資料（免 API 金鑰）。

    使用 XRPL 公開 JSON-RPC 端點，呼叫標準 XRPL RPC 方法。
    不需要 API 金鑰，直接使用社群維護的公開節點。

    支援指標：tx_count, ledger_info, fee, reserve, validator_count
    若 metrics 為空或 None，則取得所有支援的指標。

    Args:
        metrics: 要取得的指標列表，例如 ["tx_count", "fee"]
        lookback_days: 回溯天數（用於資料時間範圍描述）

    Returns:
        統一格式 dict：成功時含 raw/source/content_reference/summary，
        失敗時含 error/source/content_reference。
    """
    _XRPL_URL = "https://xrplcluster.com"
    _XRPL_FALLBACK_URL = "https://s1.ripple.com:51234"
    _SUPPORTED_XRP_METRICS = {"tx_count", "ledger_info", "fee", "reserve", "validator_count"}

    source_url = f"{_XRPL_URL} (XRPL public node)"
    start_time = time.time()
    endpoints_called = []

    try:
        # 決定要查詢哪些指標
        if not metrics:
            requested_metrics = _SUPPORTED_XRP_METRICS.copy()
        else:
            if isinstance(metrics, str):
                metrics = [metrics]
            requested_metrics = set(metrics) & _SUPPORTED_XRP_METRICS
            if not requested_metrics:
                requested_metrics = _SUPPORTED_XRP_METRICS.copy()

        raw_data = {}
        active_url = _XRPL_URL

        def _rpc_call(method, params=None):
            """呼叫 XRPL JSON-RPC 方法，失敗時嘗試 fallback 節點。"""
            nonlocal active_url
            endpoints_called.append(f"{active_url}/{method}")
            payload = {"method": method, "params": [params or {}]}
            try:
                resp = requests.post(
                    active_url,
                    json=payload,
                    timeout=_TIMEOUT,
                    headers={**_HEADERS, "Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                result = data.get("result", {})
                if result.get("status") != "success":
                    raise RuntimeError(f"XRPL RPC error: {result.get('error', 'unknown')}")
                return result
            except Exception:
                # 嘗試 fallback 節點
                if active_url == _XRPL_URL:
                    active_url = _XRPL_FALLBACK_URL
                    endpoints_called.append(f"{active_url}/{method} (fallback)")
                    resp = requests.post(
                        active_url,
                        json=payload,
                        timeout=_TIMEOUT,
                        headers={**_HEADERS, "Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    result = data.get("result", {})
                    if result.get("status") != "success":
                        raise RuntimeError(f"XRPL RPC error: {result.get('error', 'unknown')}")
                    return result
                else:
                    raise

        # --- ledger_info / tx_count: 從 ledger 方法取得 ---
        if "ledger_info" in requested_metrics or "tx_count" in requested_metrics:
            ledger_result = _rpc_call("ledger", {
                "ledger_index": "validated",
                "transactions": True,
                "expand": False,
            })
            ledger = ledger_result.get("ledger", {})
            ledger_index = ledger.get("ledger_index") or ledger.get("seqNum")
            close_time = ledger.get("close_time_human", "")
            ledger_hash = ledger.get("ledger_hash") or ledger.get("hash", "")
            transactions = ledger.get("transactions", [])
            tx_count = len(transactions) if isinstance(transactions, list) else 0

            if "ledger_info" in requested_metrics:
                raw_data["ledger_info"] = {
                    "ledger_index": ledger_index,
                    "close_time_human": close_time,
                    "ledger_hash": ledger_hash,
                    "tx_count_in_ledger": tx_count,
                    "total_coins": ledger.get("total_coins", ""),
                    "close_time_resolution": ledger.get("close_time_resolution"),
                }

            if "tx_count" in requested_metrics:
                raw_data["tx_count"] = {
                    "latest_validated_ledger": ledger_index,
                    "tx_count_in_latest_ledger": tx_count,
                    "close_time": close_time,
                }

        # --- fee: 從 fee 方法取得 ---
        if "fee" in requested_metrics:
            fee_result = _rpc_call("fee")
            drops = fee_result.get("drops", {})
            raw_data["fee"] = {
                "open_ledger_fee": drops.get("open_ledger_fee", ""),
                "minimum_fee": drops.get("minimum_fee", ""),
                "median_fee": drops.get("median_fee", ""),
                "base_fee": drops.get("base_fee", ""),
                "current_queue_size": fee_result.get("current_queue_size"),
                "expected_ledger_size": fee_result.get("expected_ledger_size"),
                "max_queue_size": fee_result.get("max_queue_size"),
                "current_ledger_size": fee_result.get("current_ledger_size"),
            }

        # --- reserve / validator_count: 從 server_info 方法取得 ---
        if "reserve" in requested_metrics or "validator_count" in requested_metrics:
            server_result = _rpc_call("server_info")
            info = server_result.get("info", {})
            validated_ledger = info.get("validated_ledger", {})

            if "reserve" in requested_metrics:
                raw_data["reserve"] = {
                    "reserve_base_xrp": validated_ledger.get("reserve_base_xrp"),
                    "reserve_inc_xrp": validated_ledger.get("reserve_inc_xrp"),
                    "base_fee_xrp": validated_ledger.get("base_fee_xrp"),
                    "load_factor": info.get("load_factor"),
                    "server_state": info.get("server_state", ""),
                    "peers": info.get("peers"),
                    "validated_ledger_seq": validated_ledger.get("seq"),
                }

            if "validator_count" in requested_metrics:
                raw_data["validator_count"] = {
                    "peers": info.get("peers"),
                    "server_state": info.get("server_state", ""),
                    "load_factor": info.get("load_factor"),
                    "uptime": info.get("uptime"),
                    "complete_ledgers": info.get("complete_ledgers", ""),
                    "validated_ledger_seq": validated_ledger.get("seq"),
                }

        # --- 組裝 content_reference ---
        content_reference = {
            "endpoints_called": endpoints_called,
            "metrics_retrieved": list(raw_data.keys()),
            "data_time_range": f"lookback_days={lookback_days}",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # --- 組裝 summary ---
        summary_parts = ["XRP 鏈上資料（來源：XRPL 公開節點）："]

        if "ledger_info" in raw_data:
            idx = raw_data["ledger_info"]["ledger_index"]
            close = raw_data["ledger_info"]["close_time_human"]
            summary_parts.append(f"最新驗證帳本 #{idx}，關閉時間 {close}")

        if "tx_count" in raw_data:
            count = raw_data["tx_count"]["tx_count_in_latest_ledger"]
            summary_parts.append(f"最新帳本交易數 {count} 筆")

        if "fee" in raw_data:
            open_fee = raw_data["fee"]["open_ledger_fee"]
            min_fee = raw_data["fee"]["minimum_fee"]
            median_fee = raw_data["fee"]["median_fee"]
            summary_parts.append(
                f"費用：開放帳本費 {open_fee} drops、最低 {min_fee} drops、中位 {median_fee} drops"
            )

        if "reserve" in raw_data:
            base = raw_data["reserve"]["reserve_base_xrp"]
            inc = raw_data["reserve"]["reserve_inc_xrp"]
            state = raw_data["reserve"]["server_state"]
            summary_parts.append(f"帳戶保留金 {base} XRP（遞增 {inc} XRP），節點狀態：{state}")

        if "validator_count" in raw_data:
            peers = raw_data["validator_count"]["peers"]
            uptime = raw_data["validator_count"]["uptime"]
            summary_parts.append(f"連接節點數 {peers}，運行時間 {uptime} 秒")

        summary = "；".join(summary_parts)

        # --- 記錄成功執行 ---
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name="fetch_xrp_onchain",
            status="success",
            elapsed_ms=elapsed_ms,
            note=f"XRP: retrieved {list(raw_data.keys())}",
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
            tool_name="fetch_xrp_onchain",
            status="error",
            elapsed_ms=elapsed_ms,
            note=f"XRP: {type(e).__name__}: {str(e)}",
        )
        return {
            "error": f"[fetch_xrp_onchain] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }