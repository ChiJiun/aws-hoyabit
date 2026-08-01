"""
defi.py — DeFi TVL 與穩定幣供給工具

資料來源：DefiLlama（免鑰、免認證）

設計考量：
- DefiLlama 提供全市場 TVL 與穩定幣供給數據，為判斷 DeFi 生態健康與資金流向的核心指標
- 穩定幣增發 = 場外資金彈藥進場；TVL 與幣價背離 = DeFi 使用量脫鉤價格
- 兩個指標各自獨立取得，單一失敗不影響另一指標回傳（partial failure OK）
- 所有外部 API 呼叫設 timeout 30 秒，失敗回傳 error dict，絕不拋出未處理例外
"""

import time
from datetime import datetime, timezone

import requests

import evidence

# ---- 常數 ----
_TIMEOUT = 30
_HEADERS = {"User-Agent": "HoyabitAgent/1.0"}
_DEFILLAMA_BASE = "https://api.llama.fi"
_STABLECOINS_BASE = "https://stablecoins.llama.fi"


def get_defi_data(metrics, chain="all", related_claim=""):
    """取得 DeFi TVL 與穩定幣供給資料。

    Args:
        metrics: 要取得的指標列表 ["tvl", "stablecoin_supply"]
        chain: 指定鏈名稱（如 "Ethereum", "Solana"）或 "all" 代表全市場
        related_claim: Agent 說明取數目的

    Returns:
        Contract C1 dict or error dict
    """
    source_url = _DEFILLAMA_BASE
    start_time = time.time()

    try:
        results = {}
        endpoints_called = []

        # ---- 處理 TVL 指標 ----
        if "tvl" in metrics:
            tvl_result = _fetch_tvl(chain)
            results["tvl"] = tvl_result
            endpoints_called.append(f"{_DEFILLAMA_BASE}/v2/chains")

        # ---- 處理穩定幣供給指標 ----
        if "stablecoin_supply" in metrics:
            stablecoin_result = _fetch_stablecoin_supply()
            results["stablecoin_supply"] = stablecoin_result
            endpoints_called.append(f"{_STABLECOINS_BASE}/stablecoins?includePrices=true")

        # 若全部指標都失敗，回傳 error dict
        all_failed = all(
            "error" in results.get(m, {"error": "not requested"})
            for m in metrics
            if m in ("tvl", "stablecoin_supply")
        )
        if all_failed and results:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msgs = "; ".join(
                results[m].get("error", "")
                for m in metrics
                if m in results and "error" in results[m]
            )
            evidence.log_execution_step(
                "get_defi_data", "error", elapsed_ms, note=error_msgs
            )
            return {
                "error": f"[get_defi_data] 所有指標取得失敗: {error_msgs}",
                "source": source_url,
                "content_reference": {},
            }

        # ---- 組裝 content_reference ----
        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        content_reference = {
            "endpoints_called": endpoints_called,
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
        }

        # TVL 資料
        total_tvl_usd = None
        chain_tvl_breakdown = {}
        if "tvl" in results and "error" not in results["tvl"]:
            tvl_data = results["tvl"]
            total_tvl_usd = tvl_data.get("total_tvl_usd")
            chain_tvl_breakdown = tvl_data.get("chain_tvl_breakdown", {})
            content_reference["total_tvl_usd"] = total_tvl_usd
            content_reference["chain_tvl_breakdown"] = chain_tvl_breakdown

        # 穩定幣資料
        stablecoin_total_supply_usd = None
        stablecoin_7d_change_pct = None
        if "stablecoin_supply" in results and "error" not in results["stablecoin_supply"]:
            sc_data = results["stablecoin_supply"]
            stablecoin_total_supply_usd = sc_data.get("total_supply_usd")
            stablecoin_7d_change_pct = sc_data.get("change_7d_pct")
            content_reference["stablecoin_total_supply_usd"] = stablecoin_total_supply_usd
            if stablecoin_7d_change_pct is not None:
                content_reference["stablecoin_7d_change_pct"] = stablecoin_7d_change_pct

        # ---- 組裝 summary ----
        summary_parts = []

        if total_tvl_usd is not None:
            tvl_b = total_tvl_usd / 1_000_000_000
            if chain.lower() != "all":
                summary_parts.append(f"{chain} TVL ${tvl_b:.1f} B")
            else:
                summary_parts.append(f"全市場 TVL ${tvl_b:.1f} B")

            # 列出 top 5 chains
            if chain_tvl_breakdown:
                top5 = sorted(chain_tvl_breakdown.items(), key=lambda x: x[1], reverse=True)[:5]
                top5_str = ", ".join(f"{name} ${v/1_000_000_000:.1f}B" for name, v in top5)
                summary_parts.append(f"Top5: {top5_str}")
        elif "tvl" in metrics:
            summary_parts.append("TVL: 取得失敗")

        if stablecoin_total_supply_usd is not None:
            sc_b = stablecoin_total_supply_usd / 1_000_000_000
            change_str = ""
            if stablecoin_7d_change_pct is not None:
                sign = "+" if stablecoin_7d_change_pct >= 0 else ""
                change_str = f"（近 7 日變化 {sign}{stablecoin_7d_change_pct:.1f}%）"
            summary_parts.append(f"穩定幣供給 ${sc_b:.1f} B{change_str}")
        elif "stablecoin_supply" in metrics:
            summary_parts.append("穩定幣供給: 取得失敗")

        summary = ", ".join(summary_parts)

        # ---- 組裝 raw ----
        raw_data = {
            "tvl": results.get("tvl", {}),
            "stablecoin_supply": results.get("stablecoin_supply", {}),
            "query_params": {
                "metrics": metrics,
                "chain": chain,
            },
        }

        # 記錄執行步驟
        evidence.log_execution_step(
            "get_defi_data", "success", elapsed_ms, note=summary[:100]
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
            "get_defi_data", "error", elapsed_ms,
            note=f"{type(e).__name__}: {str(e)}"
        )
        return {
            "error": f"[get_defi_data] {type(e).__name__}: {str(e)}",
            "source": source_url,
            "content_reference": {},
        }


def _fetch_tvl(chain):
    """取得 TVL 資料，依 chain 參數決定全市場或特定鏈。

    回傳 dict 含 total_tvl_usd 與 chain_tvl_breakdown（top chains）。
    失敗回傳含 error key 的 dict。
    """
    try:
        # GET /v2/chains 回傳所有鏈的 TVL
        url = f"{_DEFILLAMA_BASE}/v2/chains"
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        chains_data = resp.json()

        if not isinstance(chains_data, list):
            return {"error": "DefiLlama /v2/chains 回傳格式異常"}

        # 計算全市場 TVL 與各鏈 breakdown
        chain_tvl_breakdown = {}
        total_tvl = 0.0

        for item in chains_data:
            chain_name = item.get("name", "Unknown")
            tvl = item.get("tvl", 0)
            if tvl and isinstance(tvl, (int, float)):
                chain_tvl_breakdown[chain_name] = tvl
                total_tvl += tvl

        # 如果指定特定鏈，過濾
        if chain.lower() != "all":
            # 嘗試不分大小寫匹配
            matched_tvl = None
            for name, tvl in chain_tvl_breakdown.items():
                if name.lower() == chain.lower():
                    matched_tvl = tvl
                    break

            if matched_tvl is not None:
                return {
                    "total_tvl_usd": matched_tvl,
                    "chain_tvl_breakdown": {chain: matched_tvl},
                    "raw_chains_count": len(chains_data),
                }
            else:
                return {"error": f"找不到鏈 '{chain}' 的 TVL 資料"}

        # 全市場：回傳 top chains breakdown
        top_chains = sorted(chain_tvl_breakdown.items(), key=lambda x: x[1], reverse=True)[:10]
        top_breakdown = dict(top_chains)

        return {
            "total_tvl_usd": total_tvl,
            "chain_tvl_breakdown": top_breakdown,
            "raw_chains_count": len(chains_data),
        }

    except Exception as e:
        return {"error": f"TVL 取得失敗: {type(e).__name__}: {str(e)}"}


def _fetch_stablecoin_supply():
    """取得穩定幣供給資料，計算總供給量與 7 日變化。

    回傳 dict 含 total_supply_usd 與 change_7d_pct。
    失敗回傳含 error key 的 dict。
    """
    try:
        url = f"{_STABLECOINS_BASE}/stablecoins?includePrices=true"
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        pegged_assets = data.get("peggedAssets", [])
        if not pegged_assets:
            return {"error": "穩定幣資料為空"}

        # 計算目前總供給（sum all peggedAssets 的 circulating.peggedUSD）
        total_supply = 0.0
        total_supply_7d_ago = 0.0

        for asset in pegged_assets:
            # 目前流通量
            circulating = asset.get("circulating", {})
            pegged_usd = circulating.get("peggedUSD", 0)
            if pegged_usd and isinstance(pegged_usd, (int, float)):
                total_supply += pegged_usd

            # 7 日前的流通量（用於計算變化百分比）
            # DefiLlama 的 stablecoins endpoint 提供 circulatingPrevDay/circulatingPrevWeek
            circulating_prev_week = asset.get("circulatingPrevWeek", {})
            prev_week_usd = circulating_prev_week.get("peggedUSD", 0)
            if prev_week_usd and isinstance(prev_week_usd, (int, float)):
                total_supply_7d_ago += prev_week_usd

        # 計算 7 日變化百分比
        change_7d_pct = None
        if total_supply_7d_ago > 0:
            change_7d_pct = round(
                ((total_supply - total_supply_7d_ago) / total_supply_7d_ago) * 100, 2
            )

        return {
            "total_supply_usd": total_supply,
            "change_7d_pct": change_7d_pct,
            "assets_count": len(pegged_assets),
        }

    except Exception as e:
        return {"error": f"穩定幣供給取得失敗: {type(e).__name__}: {str(e)}"}


# ---- Symbol → GitHub Repo 映射表 ----
_SYMBOL_TO_REPO = {
    "BTC": ("bitcoin", "bitcoin"),
    "ETH": ("ethereum", "go-ethereum"),
    "SOL": ("solana-labs", "solana"),
    "BNB": ("bnb-chain", "bsc"),
    "XRP": ("XRPLF", "rippled"),
}

_GITHUB_API_BASE = "https://api.github.com"


def get_dev_activity(symbol, related_claim):
    """取得指定幣種專案的 GitHub 開發活躍度。"""
    source_url = _GITHUB_API_BASE
    start_time = time.time()
    symbol_upper = symbol.upper().strip()

    try:
        if symbol_upper not in _SYMBOL_TO_REPO:
            return {"error": f"[get_dev_activity] 不支援的幣種: {symbol_upper}，支援: {list(_SYMBOL_TO_REPO.keys())}"}

        owner, repo = _SYMBOL_TO_REPO[symbol_upper]
        endpoints_called = []
        results = {}

        # Commit activity (last 4 weeks)
        try:
            url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/stats/commit_activity"
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            endpoints_called.append(url)
            if isinstance(data, list) and len(data) >= 4:
                last_4_weeks = data[-4:]
                commit_count_4w = sum(week.get("total", 0) for week in last_4_weeks)
                results["commit_count_4w"] = commit_count_4w
        except Exception as e:
            results["commit_error"] = str(e)

        # Latest release
        try:
            url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/releases/latest"
            resp = requests.get(url, headers={**_HEADERS, "Accept": "application/vnd.github+json"}, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            endpoints_called.append(url)
            results["latest_release_tag"] = data.get("tag_name", "")
            results["latest_release_date"] = data.get("published_at", "")
            results["latest_release_name"] = data.get("name", "")
        except Exception:
            results["latest_release_tag"] = "N/A"
            results["latest_release_date"] = ""

        elapsed_ms = int((time.time() - start_time) * 1000)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # Summary
        commit_str = f"近 4 週 commit 數 {results.get('commit_count_4w', 'N/A')}"
        release_str = f"最新 release: {results.get('latest_release_tag', 'N/A')}"
        if results.get("latest_release_date"):
            release_str += f" ({results['latest_release_date'][:10]})"
        summary = f"{symbol_upper} GitHub ({owner}/{repo}): {commit_str}, {release_str}"

        content_reference = {
            "endpoints_called": endpoints_called,
            "repo": f"{owner}/{repo}",
            "symbol": symbol_upper,
            "fetched_at": fetched_at,
            "elapsed_ms": elapsed_ms,
        }
        content_reference.update({k: v for k, v in results.items() if not k.endswith("_error")})

        evidence.log_execution_step("get_dev_activity", "success", elapsed_ms, note=summary[:100])

        return {
            "raw": results,
            "source": f"{_GITHUB_API_BASE}/repos/{owner}/{repo}",
            "content_reference": content_reference,
            "summary": summary,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step("get_dev_activity", "error", elapsed_ms, note=str(e))
        return {"error": f"[get_dev_activity] {type(e).__name__}: {str(e)}", "source": source_url, "content_reference": {}}
