"""
agent.py — Agent 主迴圈與工具規格

這是整個系統的核心。run_agent_loop 維持「呼叫模型 → 判斷模型是否要用工具
→ 分派到對應工具 → 把結果餵回模型」的循環，直到模型認為證據足夠。
"""

import re
import time
import json
import concurrent.futures
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import boto3
from botocore.exceptions import ClientError

import config
import evidence
from tools import price, news, onchain, quant, sentiment, macro
from tools import derivatives, prediction, defi, institutional

# 工具名稱與實際函式的對應表。
# 這裡的 key 必須跟 build_tool_config() 裡宣告的 toolSpec name 完全一致，
# 否則模型呼叫工具時會找不到對應函式。
TOOL_DISPATCH = {
    "get_price_ohlcv": price.get_price_ohlcv,
    "search_news": news.search_news,
    "get_onchain": onchain.get_onchain,
    "compute_quant": quant.compute_quant,
    "get_sentiment": sentiment.get_sentiment,
    "get_macro": macro.get_macro,
    "get_derivatives": derivatives.get_derivatives,
    "get_prediction_market": prediction.get_prediction_market,
    "get_defi_data": defi.get_defi_data,
    "get_dev_activity": defi.get_dev_activity,
    "get_orderbook_depth": price.get_orderbook_depth,
    "get_market_dominance": price.get_market_dominance,
    "get_cftc_cot": institutional.get_cftc_cot,
    "get_sec_filings": institutional.get_sec_filings,
    "get_coin_metrics": institutional.get_coin_metrics,
}



SYSTEM_PROMPT = """你是加密市場分析助理。使用者會給你一個或兩個幣種以及一個分析題目，
你要蒐集多方資料，產出一份有證據支撐的分析。你不做投資建議
（不說買進、賣出、目標價），你只做資訊的整理與判斷。

如果收到兩個幣種，代表這是比較分析題型，你必須確保兩邊都有對等的分析深度，
並且用 compute_quant 的 compare_symbol 參數計算兩者的相關係數。

你有兩層工具可用：

【核心資料】大多數題目都會用到，優先考慮：
- get_price_ohlcv、compute_quant（價格與技術指標）
- search_news（新聞與公告）
- get_onchain（鏈上活躍度）
- get_sentiment、get_macro（市場情緒與總經環境，視題目相關性決定是否查詢）

【進階資料】只在題目明確需要更深入的市場結構或機構視角時才查，
不要為了展現豐富度而每次都查：
- get_derivatives（衍生品/槓桿方向）：適合討論波動性、方向性壓力的題目
- get_prediction_market（預測市場定價）：適合討論特定事件（如 ETF、監管）的題目
- get_defi_data（DeFi 資金流向）：適合討論資金輪動、場外資金進場的題目
- get_dev_activity（開發活躍度）：適合討論基本面健康度的題目
- get_orderbook_depth（盤口深度）：適合討論短期流動性風險的題目
- get_market_dominance（市值占比）：適合比較分析題型，判斷資金輪動方向
- get_cftc_cot（機構持倉，僅 BTC）：適合討論機構情緒、smart money 方向的題目
- get_sec_filings（監管文件）：適合討論監管動態、ETF 進度的題目
- get_coin_metrics（機構級估值指標）：適合討論估值是否合理的題目

工作步驟：

1. 問題驅動的多維度規劃：
   先辨識與題目相關的子問題，選擇至少 2 個能回答不同子問題、彼此互補且與題目相關的分析維度。
   若是比較兩個幣種，必須在相同的相關維度下比較；不要為了湊數量而查無關資料，
   也不預設固定工具數量或固定呼叫順序。

2. 動態蒐集足夠證據：
   依子問題呼叫足夠的相關工具。每次呼叫工具時，related_claim 欄位必填，說明「這筆資料要用來檢驗什麼」。
   「至少 3 個不同證據來源類別」只是一項匯出驗證政策，不是報告分母、覆蓋率、維度分數或強制蒐集配額。
   若相關工具失敗，保留原因並以其他相關證據繼續分析。

3. 交叉驗證與背離偵測：
   對實際使用的維度，明確比較一致訊號、背離訊號或證據不足；來源矛盾時說明取捨依據。
   可在題目與證據相關時檢查這些背離模式：
   - 資金費率轉負 + 價格持平：空頭擁擠但價格未進一步下跌
   - OI 新高 + 波動率壓縮：槓桿堆積但波動尚未釋放
   - DVOL 抬升 + 已實現波動率低：期權市場正為潛在事件風險定價

4. 結構化分析：
   - 事實(fact)：資料直接顯示的數字或事件，必須引用存在的 evidence_id
   - 推論(inference)：由事實推導的判斷與邏輯
   - 結論(conclusion)：綜合多項推論得出的判斷
   不得以沒有 evidence_id 的事實支撐結論。

5. 誠實說明信心與限制：
   - 只列出與題目相關但省略，或實際嘗試後失敗／無法取得的維度及原因
   - 說明這些缺口如何影響結論信心，不列舉無關且未嘗試的維度
   - 有矛盾訊號時，說明矛盾內容、取捨與理由
   - 說明什麼情況會推翻結論
   資料不足時就說「無法給出高信心判斷」，不要硬湊結論。

重要規則：
- 所有數字運算（技術指標、百分位、相關係數）都要透過 compute_quant 工具計算，不要自己心算。
"""


# ---- Request-scoped state (cleared per request) ----
_run_context: dict = {}
_series_registry: dict = {}


# ===========================================================================
# Phase A: Question Classification & Prefetch Orchestration
# ===========================================================================

@dataclass
class QuestionTypeResult:
    question_type: str  # single_integration | hypothesis | comparison
    method: str  # rule | llm_fallback
    matched_rules: list


_HYPOTHESIS_PATTERN = re.compile(
    r"認為|觀點|驗證|假設|是否正確|是否成立|有人說|市場認為|聲音認為|市場預期|是否會|能否"
)


def classify_question_type(symbols: list, question: str) -> QuestionTypeResult:
    """Rule-based question type classification.

    Rule 1: len(symbols) == 2 → comparison
    Rule 2: hypothesis keywords regex → hypothesis
    Rule 3: default → single_integration
    """
    matched_rules = []

    # Rule 1: comparison
    if len(symbols) == 2:
        matched_rules.append("rule1_two_symbols")
        result = QuestionTypeResult(
            question_type="comparison",
            method="rule",
            matched_rules=matched_rules,
        )
        evidence.log_execution_step(
            "classify_question_type", "success", 0,
            note=f"type=comparison matched={matched_rules}"
        )
        return result

    # Rule 2: hypothesis keywords
    if _HYPOTHESIS_PATTERN.search(question):
        matched_rules.append("rule2_hypothesis_keywords")
        result = QuestionTypeResult(
            question_type="hypothesis",
            method="rule",
            matched_rules=matched_rules,
        )
        evidence.log_execution_step(
            "classify_question_type", "success", 0,
            note=f"type=hypothesis matched={matched_rules}"
        )
        return result

    # Rule 3: default
    matched_rules.append("rule3_default")
    result = QuestionTypeResult(
        question_type="single_integration",
        method="rule",
        matched_rules=matched_rules,
    )
    evidence.log_execution_step(
        "classify_question_type", "success", 0,
        note=f"type=single_integration matched={matched_rules}"
    )
    return result


@dataclass
class PrefetchItem:
    capability: str
    tool_name: str
    tool_kwargs: dict
    symbols: list
    reason: str
    required: bool = True
    timeout_seconds: float = 30.0


def build_prefetch_plan(question_type: str, symbols: list, question: str) -> list:
    """Build a list of PrefetchItem for Phase A parallel data gathering.

    Common per-symbol: price, quant, derivatives_hl, derivatives_binance, news, onchain
    Common once: sentiment, macro
    Type additions:
      single_integration → defi_stablecoin + prediction
      hypothesis → defi_stablecoin + prediction + directed_news
      comparison → correlation + dominance
    """
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

    plan: list = []

    # --- Common per-symbol items ---
    for sym in symbols:
        # price
        plan.append(PrefetchItem(
            capability="price",
            tool_name="get_price_ohlcv",
            tool_kwargs={
                "symbol": sym,
                "start_date": start_date,
                "end_date": current_date,
                "related_claim": f"取得 {sym} 近 30 天價格走勢以分析趨勢方向",
            },
            symbols=[sym],
            reason="core price data",
        ))
        # quant
        plan.append(PrefetchItem(
            capability="quant",
            tool_name="compute_quant",
            tool_kwargs={
                "symbol": sym,
                "features": ["atr_pct", "bollinger_bandwidth", "adx", "volume_zscore", "realized_vol"],
                "window": 14,
                "related_claim": f"計算 {sym} 技術指標以評估波動與趨勢強度",
            },
            symbols=[sym],
            reason="technical indicators",
        ))
        # derivatives - hyperliquid
        plan.append(PrefetchItem(
            capability="derivatives_hl",
            tool_name="get_derivatives",
            tool_kwargs={
                "symbol": sym,
                "source": "hyperliquid",
                "metrics": ["funding_rate", "open_interest", "liquidations"],
                "related_claim": f"取得 {sym} Hyperliquid 衍生品數據以評估槓桿方向",
            },
            symbols=[sym],
            reason="derivatives hyperliquid",
            required=False,
        ))
        # derivatives - binance
        plan.append(PrefetchItem(
            capability="derivatives_binance",
            tool_name="get_derivatives",
            tool_kwargs={
                "symbol": sym,
                "source": "binance_futures",
                "metrics": ["funding_rate", "open_interest", "long_short_ratio"],
                "related_claim": f"取得 {sym} Binance 衍生品數據以評估散戶情緒",
            },
            symbols=[sym],
            reason="derivatives binance",
            required=False,
        ))
        # news
        plan.append(PrefetchItem(
            capability="news",
            tool_name="search_news",
            tool_kwargs={
                "symbol": sym,
                "lookback_days": 14,
                "related_claim": f"搜尋 {sym} 近期新聞以了解市場催化劑",
            },
            symbols=[sym],
            reason="recent news",
        ))
        # onchain
        plan.append(PrefetchItem(
            capability="onchain",
            tool_name="get_onchain",
            tool_kwargs={
                "symbol": sym,
                "metrics": ["active_addresses", "tx_count", "exchange_netflow"],
                "lookback_days": 14,
                "related_claim": f"取得 {sym} 鏈上活躍度以評估網路使用狀況",
            },
            symbols=[sym],
            reason="onchain activity",
        ))

    # --- Common once items ---
    plan.append(PrefetchItem(
        capability="sentiment",
        tool_name="get_sentiment",
        tool_kwargs={
            "related_claim": "取得市場恐懼貪婪指數以評估整體情緒",
        },
        symbols=symbols,
        reason="market sentiment",
    ))
    plan.append(PrefetchItem(
        capability="macro",
        tool_name="get_macro",
        tool_kwargs={
            "indicators": ["DXY", "US10Y", "FEDFUNDS"],
            "related_claim": "取得總經指標以評估宏觀環境對加密市場影響",
        },
        symbols=symbols,
        reason="macro environment",
    ))

    # --- Type-specific additions ---
    if question_type == "single_integration":
        plan.append(PrefetchItem(
            capability="defi_stablecoin",
            tool_name="get_defi_data",
            tool_kwargs={
                "metrics": ["tvl", "stablecoin_supply"],
                "chain": "all",
                "related_claim": "取得 DeFi TVL 與穩定幣供給量以評估資金流入",
            },
            symbols=symbols,
            reason="defi stablecoin supply",
            required=False,
        ))
        plan.append(PrefetchItem(
            capability="prediction",
            tool_name="get_prediction_market",
            tool_kwargs={
                "keywords": " ".join(symbols) + " crypto",
                "related_claim": "查詢預測市場以了解市場對重大事件的定價",
            },
            symbols=symbols,
            reason="prediction market",
            required=False,
        ))
    elif question_type == "hypothesis":
        plan.append(PrefetchItem(
            capability="defi_stablecoin",
            tool_name="get_defi_data",
            tool_kwargs={
                "metrics": ["tvl", "stablecoin_supply"],
                "chain": "all",
                "related_claim": "取得 DeFi TVL 與穩定幣供給量以驗證假設",
            },
            symbols=symbols,
            reason="defi stablecoin supply",
            required=False,
        ))
        plan.append(PrefetchItem(
            capability="prediction",
            tool_name="get_prediction_market",
            tool_kwargs={
                "keywords": " ".join(symbols) + " crypto",
                "related_claim": "查詢預測市場以驗證假設的市場共識",
            },
            symbols=symbols,
            reason="prediction market",
            required=False,
        ))
        # directed news with question keywords
        plan.append(PrefetchItem(
            capability="directed_news",
            tool_name="search_news",
            tool_kwargs={
                "symbol": symbols[0],
                "lookback_days": 14,
                "related_claim": "搜尋與假設直接相關的新聞以驗證觀點",
                "keywords": question[:50],
            },
            symbols=symbols,
            reason="hypothesis-directed news",
            required=False,
        ))
    elif question_type == "comparison":
        # correlation
        plan.append(PrefetchItem(
            capability="correlation",
            tool_name="compute_quant",
            tool_kwargs={
                "symbol": symbols[0],
                "features": ["correlation"],
                "window": 30,
                "related_claim": f"計算 {symbols[0]} 與 {symbols[1]} 的相關係數以比較聯動性",
                "compare_symbol": symbols[1],
            },
            symbols=symbols,
            reason="cross-correlation",
        ))
        # dominance
        plan.append(PrefetchItem(
            capability="dominance",
            tool_name="get_market_dominance",
            tool_kwargs={
                "related_claim": "取得市值佔比以比較兩幣種資金輪動方向",
            },
            symbols=symbols,
            reason="market dominance",
            required=False,
        ))

    # Deduplicate sentiment and macro (already only added once above)
    return plan



@dataclass
class PrefetchOutcome:
    question_type: str
    started_at: str
    completed_at: str
    results: list = field(default_factory=list)
    missing: list = field(default_factory=list)


def _execute_prefetch_item(item: PrefetchItem, run_id: str) -> dict:
    """Execute a single prefetch item and return result dict.

    Isolates failures so one tool crash doesn't affect others.
    """
    start_time = time.time()
    tool_name = item.tool_name

    if tool_name not in TOOL_DISPATCH:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(
            tool_name, "error", elapsed_ms, note="unknown tool in prefetch"
        )
        return {
            "capability": item.capability,
            "tool_name": tool_name,
            "status": "error",
            "error": f"Unknown tool: {tool_name}",
            "symbols": item.symbols,
        }

    func = TOOL_DISPATCH[tool_name]

    try:
        result = func(**item.tool_kwargs)
        elapsed_ms = int((time.time() - start_time) * 1000)

        if isinstance(result, dict) and "error" in result:
            evidence.log_execution_step(
                tool_name, "error", elapsed_ms, note=result["error"]
            )
            return {
                "capability": item.capability,
                "tool_name": tool_name,
                "status": "error",
                "error": result["error"],
                "symbols": item.symbols,
            }

        # Record evidence
        related_claim = item.tool_kwargs.get("related_claim", "prefetch data")
        evidence_id = evidence.log_evidence(run_id, tool_name, related_claim, result)

        if isinstance(evidence_id, dict) and "error" in evidence_id:
            evidence.log_execution_step(
                tool_name, "warning", elapsed_ms, note=evidence_id["error"]
            )
            evidence_id = None

        evidence.log_execution_step(
            tool_name, "success", elapsed_ms, evidence_id=evidence_id
        )

        return {
            "capability": item.capability,
            "tool_name": tool_name,
            "status": "success",
            "evidence_id": evidence_id,
            "summary": result.get("summary", ""),
            "anomaly_flags": result.get("anomaly_flags", []),
            "symbols": item.symbols,
            "raw_result": result,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_msg = f"[{tool_name}] {type(e).__name__}: {str(e)}"
        evidence.log_execution_step(tool_name, "error", elapsed_ms, note=error_msg)
        return {
            "capability": item.capability,
            "tool_name": tool_name,
            "status": "error",
            "error": error_msg,
            "symbols": item.symbols,
        }


def run_phase_a_prefetch(run_id: str, plan: list, soft_deadline_seconds: float = 90.0) -> PrefetchOutcome:
    """Execute all prefetch items in parallel with a soft deadline.

    Uses ThreadPoolExecutor(max_workers=8). Individual tool failures are
    isolated and recorded in the outcome's missing list.
    """
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    outcome = PrefetchOutcome(
        question_type="",
        started_at=started_at,
        completed_at="",
    )

    if not plan:
        outcome.completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return outcome

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_item = {
            executor.submit(_execute_prefetch_item, item, run_id): item
            for item in plan
        }

        try:
            done_iter = concurrent.futures.as_completed(
                future_to_item, timeout=soft_deadline_seconds
            )
            for future in done_iter:
                item = future_to_item[future]
                try:
                    result = future.result(timeout=0)
                    if result.get("status") == "success":
                        outcome.results.append(result)
                        # 由 Phase A 結果註冊視覺化序列。
                        # 不可只依賴 Phase B：LLM 是否重複呼叫價格工具並不確定，
                        # 少了這步圖表就會變成非決定性的。
                        try:
                            _extract_and_register_series(result)
                        except Exception:
                            pass  # 視覺化為加值功能，失敗不得影響資料蒐集
                    else:
                        outcome.missing.append({
                            "capability": item.capability,
                            "tool_name": item.tool_name,
                            "reason": result.get("error", "unknown error"),
                            "required": item.required,
                        })
                except Exception as exc:
                    outcome.missing.append({
                        "capability": item.capability,
                        "tool_name": item.tool_name,
                        "reason": f"{type(exc).__name__}: {str(exc)}",
                        "required": item.required,
                    })

        except concurrent.futures.TimeoutError:
            # Cancel pending futures after deadline
            for future, item in future_to_item.items():
                if not future.done():
                    future.cancel()
                    outcome.missing.append({
                        "capability": item.capability,
                        "tool_name": item.tool_name,
                        "reason": "soft_deadline_exceeded",
                        "required": item.required,
                    })

            evidence.log_execution_step(
                "phase_a_prefetch", "timeout",
                int(soft_deadline_seconds * 1000),
                note=f"Soft deadline {soft_deadline_seconds}s exceeded, some items cancelled"
            )

    outcome.completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence.log_execution_step(
        "phase_a_prefetch", "success",
        0,
        note=f"completed={len(outcome.results)} missing={len(outcome.missing)}"
    )
    return outcome



def build_phase_b_context(outcome: PrefetchOutcome) -> str:
    """Build structured text context from Phase A results for injection into Phase B.

    Contains summaries, evidence_ids, anomaly_flags, missing items - NO raw data.
    """
    sections = []
    sections.append("【Phase A 預取結果摘要】")
    sections.append(f"開始：{outcome.started_at} / 完成：{outcome.completed_at}")
    sections.append(f"成功取得 {len(outcome.results)} 項資料，{len(outcome.missing)} 項缺失\n")

    # Group results by capability
    if outcome.results:
        sections.append("── 已取得資料 ──")
        for r in outcome.results:
            evidence_id = r.get("evidence_id", "N/A")
            summary = r.get("summary", "")[:200]
            anomalies = r.get("anomaly_flags", [])
            symbols_str = ",".join(r.get("symbols", []))
            line = f"• [{r['capability']}] {r['tool_name']} ({symbols_str}) → evidence_id={evidence_id}"
            sections.append(line)
            if summary:
                sections.append(f"  摘要：{summary}")
            if anomalies:
                sections.append(f"  ⚠ 異常標記：{anomalies}")
        sections.append("")

    # Missing items
    if outcome.missing:
        sections.append("── 缺失資料 ──")
        for m in outcome.missing:
            req_label = "必要" if m.get("required") else "選用"
            sections.append(
                f"• [{m['capability']}] {m['tool_name']} ({req_label}) - 原因：{m['reason']}"
            )
        sections.append("")

    return "\n".join(sections)


def should_force_convergence(started_at_timestamp: float, budget_seconds: float) -> bool:
    """Check if remaining time is less than 20% of budget → force convergence."""
    elapsed = time.time() - started_at_timestamp
    remaining = budget_seconds - elapsed
    threshold = budget_seconds * 0.2
    return remaining < threshold


def build_question_type_prompt(question_type: str, symbols: list) -> str:
    """Generate per-type prompt additions for system prompt."""
    if question_type == "comparison":
        return (
            f"\n\n【題型提示：比較分析】本次比較 {symbols[0]} vs {symbols[1]}。"
            "Phase A 已預取兩幣種的核心資料和相關係數。"
            "請在相同維度下進行對等深度的比較分析，突出差異與關聯。"
            "不需要重複呼叫 Phase A 已成功取得的工具，除非需要更細粒度的資料。"
        )
    elif question_type == "hypothesis":
        return (
            f"\n\n【題型提示：假設驗證】本次需要驗證使用者提出或引用的觀點/假設。"
            "Phase A 已預取核心資料與相關新聞。"
            "請明確列出假設、尋找支持與反對的證據，最終給出假設成立的信心程度。"
            "不需要重複呼叫 Phase A 已成功取得的工具，除非需要更細粒度的資料。"
        )
    else:  # single_integration
        return (
            f"\n\n【題型提示：單幣整合分析】本次分析 {symbols[0]}。"
            "Phase A 已預取核心多維度資料。"
            "請整合已有資料，只在需要補充更細粒度或 Phase A 缺失的維度時才呼叫額外工具。"
            "不需要重複呼叫 Phase A 已成功取得的工具。"
        )



# ===========================================================================
# Series Registry — for visualization data extraction
# ===========================================================================

SERIES_CAPABLE_CAPABILITIES = {
    "price": "price_series",
    "quant": "indicator_series",
    "derivatives_hl": "derivatives_series",
    "derivatives_binance": "derivatives_series",
    "sentiment": "sentiment_series",
    "macro": "macro_series",
    "onchain": "onchain_series",
}


def register_visualization_series(series_id: str, series_type: str, data: dict):
    """Register a time-series data set for visualization."""
    _series_registry[series_id] = {
        "series_type": series_type,
        "data": data,
        "registered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def collect_series() -> dict:
    """Return all registered series for the current request."""
    return dict(_series_registry)


def reset_series_registry():
    """Clear the series registry for a new request."""
    _series_registry.clear()


def _extract_price_series(result: dict, symbols: list):
    """Extract OHLCV price series from a price tool result."""
    raw = result.get("raw_result", {})
    raw_data = raw.get("raw", {})

    if not raw_data:
        return

    # raw_data can be a list (OHLCV rows) or a dict with a nested list
    ohlcv = None
    if isinstance(raw_data, list):
        ohlcv = raw_data
    elif isinstance(raw_data, dict):
        ohlcv = raw_data.get("ohlcv", raw_data.get("daily", []))

    if ohlcv and isinstance(ohlcv, list):
        sym = symbols[0] if symbols else "UNKNOWN"
        series_id = f"price_{sym.lower()}_daily"
        register_visualization_series(series_id, "price_series", {
            "symbol": sym,
            "data_points": len(ohlcv),
            "series": ohlcv[-30:],  # last 30 data points max
        })


def _extract_and_register_series(result: dict):
    """Extract and register visualization series from a prefetch/tool result.

    Checks if the capability is series-capable and extracts relevant data.
    """
    capability = result.get("capability", "")
    symbols = result.get("symbols", [])
    series_type = SERIES_CAPABLE_CAPABILITIES.get(capability)

    if not series_type:
        return

    if capability == "price":
        _extract_price_series(result, symbols)
    elif capability == "quant":
        raw = result.get("raw_result", {})
        indicators = raw.get("raw", {}).get("indicators", {})
        if indicators:
            sym = symbols[0] if symbols else "UNKNOWN"
            series_id = f"quant_{sym.lower()}_indicators"
            register_visualization_series(series_id, "indicator_series", {
                "symbol": sym,
                "indicators": indicators,
            })
    elif capability in ("derivatives_hl", "derivatives_binance"):
        raw = result.get("raw_result", {})
        raw_data = raw.get("raw", {})
        if raw_data:
            sym = symbols[0] if symbols else "UNKNOWN"
            source = "hl" if capability == "derivatives_hl" else "binance"
            series_id = f"derivatives_{sym.lower()}_{source}"
            register_visualization_series(series_id, "derivatives_series", {
                "symbol": sym,
                "source": source,
                "data": raw_data,
            })
    elif capability == "sentiment":
        raw = result.get("raw_result", {})
        raw_data = raw.get("raw", {})
        if raw_data:
            series_id = "sentiment_fgi"
            register_visualization_series(series_id, "sentiment_series", {
                "data": raw_data,
            })
    elif capability == "macro":
        raw = result.get("raw_result", {})
        raw_data = raw.get("raw", {})
        if raw_data:
            series_id = "macro_indicators"
            register_visualization_series(series_id, "macro_series", {
                "data": raw_data,
            })
    elif capability == "onchain":
        raw = result.get("raw_result", {})
        raw_data = raw.get("raw", {})
        if raw_data:
            sym = symbols[0] if symbols else "UNKNOWN"
            series_id = f"onchain_{sym.lower()}"
            register_visualization_series(series_id, "onchain_series", {
                "symbol": sym,
                "data": raw_data,
            })



# ===========================================================================
# Tool Configuration & Bedrock API
# ===========================================================================

def build_tool_config():
    """組出 Bedrock Converse API 的 toolConfig JSON。

    每個 toolSpec 的 inputSchema 都把 related_claim 列為 required，
    這是強制 LLM 說明取數目的的機制。
    回傳：dict，可直接傳給 converse() 的 toolConfig 參數。
    """
    tools = [
        {
            "toolSpec": {
                "name": "get_price_ohlcv",
                "description": "取得指定幣種在指定期間的日線 OHLCV（開高低收量）資料。回答目前/近期市場問題時，end_date 必須使用系統提供的目前 UTC 日期，建議查最近 30 天。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "幣種代號，如 BTC、ETH、SOL、BNB、XRP"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "起始日期，格式 YYYY-MM-DD"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "結束日期，格式 YYYY-MM-DD"
                            },
                            "related_claim": {
                                "type": "string",
                                "description": "這筆資料要用來檢驗什麼判斷（必填，至少 5 個字）"
                            }
                        },
                        "required": ["symbol", "start_date", "end_date", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "search_news",
                "description": "查詢指定幣種近期且在 lookback_days 範圍內的新聞、官方公告與監管消息。回答目前/近期市場問題時建議 lookback_days=14；不得引用範圍外舊聞。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "幣種代號，如 BTC、ETH、SOL、BNB、XRP"
                            },
                            "lookback_days": {
                                "type": "integer",
                                "description": "往回查幾天的新聞，建議 7-30"
                            },
                            "related_claim": {
                                "type": "string",
                                "description": "這筆資料要用來檢驗什麼判斷（必填，至少 5 個字）"
                            },
                            "keywords": {
                                "type": "string",
                                "description": "額外的搜尋關鍵字（選填）"
                            }
                        },
                        "required": ["symbol", "lookback_days", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_onchain",
                "description": "取得指定幣種的鏈上活躍度指標，如活躍地址數、交易量、交易所淨流入等。用於觀察鏈上行為變化。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "幣種代號，如 BTC、ETH、SOL、BNB、XRP"
                            },
                            "metrics": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "要查詢的指標清單，如 ['active_addresses', 'tx_count', 'exchange_netflow']"
                            },
                            "lookback_days": {
                                "type": "integer",
                                "description": "往回查幾天的鏈上資料"
                            },
                            "related_claim": {
                                "type": "string",
                                "description": "這筆資料要用來檢驗什麼判斷（必填，至少 5 個字）"
                            }
                        },
                        "required": ["symbol", "metrics", "lookback_days", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "compute_quant",
                "description": "計算技術指標（ATR%、布林帶寬、ADX、成交量 Z-score、已實現波動率、相關係數等）。所有數字必須由此工具計算，不可心算。每個指標附帶百分位排名。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "幣種代號，如 BTC、ETH、SOL、BNB、XRP"
                            },
                            "features": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "要計算的指標清單，可選：atr_pct、bollinger_bandwidth、adx、volume_zscore、realized_vol、correlation、range_ratio"
                            },
                            "window": {
                                "type": "integer",
                                "description": "計算窗口天數，如 14、20、30"
                            },
                            "related_claim": {
                                "type": "string",
                                "description": "這筆資料要用來檢驗什麼判斷（必填，至少 5 個字）"
                            },
                            "compare_symbol": {
                                "type": "string",
                                "description": "比較幣種代號（計算相關係數時使用，選填）"
                            }
                        },
                        "required": ["symbol", "features", "window", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_sentiment",
                "description": "取得市場恐懼與貪婪指數（Fear & Greed Index）的當前值與近期走勢。這是全市場指數，非單一幣種專屬。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "related_claim": {
                                "type": "string",
                                "description": "這筆資料要用來檢驗什麼判斷（必填，至少 5 個字）"
                            },
                            "lookback_days": {
                                "type": "integer",
                                "description": "往回查幾天的情緒資料，預設 30"
                            }
                        },
                        "required": ["related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_macro",
                "description": "取得總體經濟指標（美元指數 DXY、10 年期公債殖利率、聯邦基金利率）與近期重要總經事件排程。用於分析宏觀環境對加密市場的影響。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "indicators": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "要查詢的總經指標清單，如 ['DXY', 'US10Y', 'FEDFUNDS']"
                            },
                            "related_claim": {
                                "type": "string",
                                "description": "這筆資料要用來檢驗什麼判斷（必填，至少 5 個字）"
                            },
                            "lookback_days": {
                                "type": "integer",
                                "description": "往回查幾天的資料，預設 90"
                            }
                        },
                        "required": ["indicators", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_derivatives",
                "description": "取得衍生品市場資料：資金費率、未平倉量(OI)、清算、隱含波動率(DVOL)、大戶多空比。"
                               "可用來源：hyperliquid（主力，免鑰）、binance_futures（備援+散戶指標）、deribit（僅BTC/ETH，期權波動率）。"
                               "訊號價值：資金費率極端=擁擠方向、OI急增+價格滯漲=槓桿堆積、DVOL vs 已實現波動率價差=市場買保險程度。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "幣種代號（BTC/ETH/SOL/BNB/XRP）"},
                            "source": {"type": "string", "description": "資料來源：hyperliquid | binance_futures | deribit"},
                            "metrics": {
                                "type": "array", "items": {"type": "string"},
                                "description": "要取得的指標。hyperliquid: funding_rate/open_interest/mark_price/liquidations; "
                                               "binance_futures: funding_rate/open_interest/long_short_ratio/taker_buy_sell_ratio; "
                                               "deribit: dvol/options_oi/put_call_ratio"
                            },
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["symbol", "source", "metrics", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_prediction_market",
                "description": "查詢 Polymarket 預測市場上加密相關事件的市場定價（機率）與成交量。"
                               "訊號價值：預測市場用真金白銀定價的共識機率，與現貨走勢比對可發現「價格未反映的預期」。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "keywords": {"type": "string", "description": "搜尋關鍵字（如 bitcoin, ETH ETF, crypto regulation）"},
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["keywords", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_defi_data",
                "description": "取得 DeFi TVL 與穩定幣供給量資料（DefiLlama 免鑰）。"
                               "訊號價值：穩定幣增發=場外資金彈藥進場、TVL 與幣價背離=DeFi 使用量脫鉤價格。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "metrics": {
                                "type": "array", "items": {"type": "string"},
                                "description": "要取得的指標：tvl / stablecoin_supply"
                            },
                            "chain": {"type": "string", "description": "指定鏈（Ethereum/Solana/BSC）或 all 代表全市場"},
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["metrics", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_dev_activity",
                "description": "取得幣種專案的 GitHub 開發活躍度（近4週 commit 數、最新 release）。"
                               "訊號價值：開發活躍度與價格背離=基本面健康但市場未反映，或反之。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "幣種代號（BTC/ETH/SOL/BNB/XRP）"},
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["symbol", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_orderbook_depth",
                "description": "取得 Binance Spot 盤口深度快照，計算目前價格 ±2% 範圍內的累積掛單量。"
                               "訊號價值：深度薄=大單容易造成滑價、買賣深度不對稱=潛在方向性壓力。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "幣種代號（BTC/ETH/SOL/BNB/XRP）"},
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["symbol", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_market_dominance",
                "description": "取得 BTC 及各幣種的市值佔比（dominance）。"
                               "訊號價值：BTC dominance 上升=資金從山寨回流比特幣（避險）、下降=資金輪動到山寨（risk-on）。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_cftc_cot",
                "description": "取得 CFTC Commitments of Traders 報告中 CME Bitcoin 期貨的機構持倉數據。"
                               "訊號價值：投機淨多頭/空頭 = smart money 方向定位，淨部位極端時常見反轉。僅 BTC 有資料。每週更新。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "目前僅支援 BTC（CME Bitcoin Futures）"},
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["symbol", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_sec_filings",
                "description": "搜尋 SEC EDGAR 近期加密相關監管文件（8-K、S-1、10-K 等）。"
                               "訊號價值：監管動態的一手來源，ETF 申請/批准、執法行動等直接影響市場的事件。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "keywords": {"type": "string", "description": "搜尋關鍵字（如 bitcoin, ethereum, crypto ETF）"},
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["keywords", "related_claim"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "get_coin_metrics",
                "description": "取得 Coin Metrics Community 的機構級鏈上/市場指標：已實現市值、MVRV 比率、NVT、活躍地址數等。"
                               "訊號價值：MVRV > 3 = 歷史性高估區、NVT 極高 = 交易活動不支撐估值。",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "幣種代號（BTC/ETH/SOL/BNB/XRP）"},
                            "metrics": {
                                "type": "array", "items": {"type": "string"},
                                "description": "指標列表，可選：RealizedCap, CapMVRVCur, NVTAdj, AdrActCnt, TxCnt, FeeMeanUSD"
                            },
                            "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                        },
                        "required": ["symbol", "metrics", "related_claim"]
                    }
                }
            }
        },
    ]

    return {"tools": tools}



def call_bedrock(messages, tool_config=None, extra_system_text=""):
    """呼叫 Bedrock Converse API 一次。

    處理 ThrottlingException（等待 2 秒重試一次）。
    回傳：API 的完整回應 dict。
    """
    client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)

    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    system_prompt = (
        SYSTEM_PROMPT
        + f"\n\n【不可忽略的時間基準】目前 UTC 日期是 {current_date}。"
        + "所有『目前／近期／短期／當前』判斷都只能使用工具回傳且資料截止日接近此日期的資料。"
        + extra_system_text
    )
    kwargs = {
        "modelId": config.BEDROCK_MODEL_ID,
        "messages": messages,
        "system": [{"text": system_prompt}],
    }
    if tool_config:
        kwargs["toolConfig"] = tool_config

    # 最多重試一次（針對 ThrottlingException）
    for attempt in range(2):
        try:
            response = client.converse(**kwargs)
            return response
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ThrottlingException" and attempt == 0:
                time.sleep(2)
                continue
            elif error_code in ("ModelTimeoutException", "ValidationException"):
                raise
            else:
                raise

    return None



def dispatch_tool_call(run_id, tool_use_block):
    """根據模型指定的工具名稱，找到對應函式並執行，然後記錄證據。

    回傳 toolResult 區塊（僅含 summary + evidence_id，不含 raw）。
    Also registers series for Phase B tool calls.
    """
    tool_name = tool_use_block["name"]
    tool_input = tool_use_block["input"]
    tool_use_id = tool_use_block["toolUseId"]

    start_time = time.time()

    # 從 TOOL_DISPATCH 找到對應函式
    if tool_name not in TOOL_DISPATCH:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step(tool_name, "error", elapsed_ms, note="unknown tool")
        return {
            "toolUseId": tool_use_id,
            "content": [{"text": json.dumps({"error": f"Unknown tool: {tool_name}"})}],
            "status": "error",
        }

    func = TOOL_DISPATCH[tool_name]

    try:
        # 執行工具函式
        result = func(**tool_input)
        elapsed_ms = int((time.time() - start_time) * 1000)

        # 檢查是否為錯誤回應
        if isinstance(result, dict) and "error" in result:
            evidence.log_execution_step(
                tool_name, "error", elapsed_ms, note=result["error"]
            )
            return {
                "toolUseId": tool_use_id,
                "content": [{"text": json.dumps({"error": result["error"]})}],
                "status": "error",
            }

        # 記錄證據
        related_claim = tool_input.get("related_claim", "")
        evidence_id = evidence.log_evidence(run_id, tool_name, related_claim, result)

        # log_evidence 可能回傳錯誤 dict（related_claim 太短時）
        if isinstance(evidence_id, dict) and "error" in evidence_id:
            evidence.log_execution_step(
                tool_name, "warning", elapsed_ms, note=evidence_id["error"]
            )
            evidence_id = None

        # 記錄執行步驟
        evidence.log_execution_step(
            tool_name, "success", elapsed_ms, evidence_id=evidence_id
        )

        # Register series for Phase B tool calls (visualization)
        _try_register_series_from_tool_call(tool_name, tool_input, result)

        # 組裝精簡的 toolResult（不含 raw，避免 context 膨脹）
        tool_result_content = {
            "summary": result.get("summary", "No summary available"),
            "evidence_id": evidence_id,
        }

        return {
            "toolUseId": tool_use_id,
            "content": [{"text": json.dumps(tool_result_content, ensure_ascii=False)}],
            "status": "success",
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_msg = f"[{tool_name}] {type(e).__name__}: {str(e)}"
        evidence.log_execution_step(tool_name, "error", elapsed_ms, note=error_msg)
        return {
            "toolUseId": tool_use_id,
            "content": [{"text": json.dumps({"error": error_msg})}],
            "status": "error",
        }


def _try_register_series_from_tool_call(tool_name: str, tool_input: dict, result: dict):
    """Attempt to register visualization series from a Phase B tool call result."""
    # Map tool_name to capability for series registration
    tool_to_capability = {
        "get_price_ohlcv": "price",
        "compute_quant": "quant",
        "get_derivatives": "derivatives_hl",
        "get_sentiment": "sentiment",
        "get_macro": "macro",
        "get_onchain": "onchain",
    }
    capability = tool_to_capability.get(tool_name)
    if not capability:
        return

    # For derivatives, distinguish source
    if tool_name == "get_derivatives":
        source = tool_input.get("source", "")
        if "binance" in source:
            capability = "derivatives_binance"

    symbols = []
    if "symbol" in tool_input:
        symbols = [tool_input["symbol"]]

    fake_result = {
        "capability": capability,
        "symbols": symbols,
        "raw_result": result,
    }
    _extract_and_register_series(fake_result)



def run_agent_loop(run_id, symbols, question):
    """系統核心。維持 Agent 的對話迴圈直到模型完成分析。

    Phase A: Parallel prefetch of core data based on question type classification.
    Phase B: LLM agent loop with prefetched context, may call additional tools.

    受 MAX_AGENT_TURNS 與 TIME_BUDGET_SECONDS 雙重限制。
    回傳：messages 陣列（完整對話歷史）。
    """
    global _run_context

    # Reset request-scoped state
    _run_context = {}
    reset_series_registry()

    loop_start = time.time()

    # ===== Phase A: Classification & Prefetch =====
    # Classify question type
    qt_result = classify_question_type(symbols, question)
    _run_context["question_type"] = qt_result.question_type
    _run_context["classification"] = {
        "question_type": qt_result.question_type,
        "method": qt_result.method,
        "matched_rules": qt_result.matched_rules,
    }

    # Build prefetch plan
    prefetch_plan = build_prefetch_plan(qt_result.question_type, symbols, question)
    _run_context["prefetch_plan_size"] = len(prefetch_plan)

    # Execute Phase A prefetch
    phase_a_outcome = run_phase_a_prefetch(run_id, prefetch_plan, soft_deadline_seconds=90.0)
    phase_a_outcome.question_type = qt_result.question_type
    _run_context["phase_a_outcome"] = {
        "started_at": phase_a_outcome.started_at,
        "completed_at": phase_a_outcome.completed_at,
        "results_count": len(phase_a_outcome.results),
        "missing_count": len(phase_a_outcome.missing),
    }

    # Extract and register series from Phase A results
    for result in phase_a_outcome.results:
        _extract_and_register_series(result)

    # Build Phase B context from Phase A outcome
    phase_b_context = build_phase_b_context(phase_a_outcome)

    # Build question type prompt addition for system prompt
    question_type_prompt = build_question_type_prompt(qt_result.question_type, symbols)

    # ===== Phase B: LLM Agent Loop =====
    # 注入時間基準，確保 LLM 使用正確日期
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    freshness_rules = (
        f"【時間基準】目前 UTC 日期是 {current_date}。凡題目提到目前、近期、短期或當前，"
        f"價格查詢 end_date 必須使用此日期，新聞使用 lookback_days=14。不得使用模型記憶中的舊日期代替。\n\n"
    )

    # 組裝題目驅動的初始 user 訊息，注入 Phase A 預取結果
    if len(symbols) == 1:
        user_text = (
            freshness_rules
            + phase_b_context + "\n\n"
            + f"幣種：{symbols[0]}\n問題：{question}\n\n"
            "請先辨識與問題相關的子問題，選擇至少 2 個能回答不同子問題且彼此互補的相關分析維度。"
            "Phase A 已預取核心資料（見上方摘要），請優先利用已有證據。"
            "只在需要更細粒度資料或 Phase A 缺失的維度時才呼叫額外工具。"
            "依分析需要動態使用足夠的工具與證據，交叉比較各維度的一致訊號、背離訊號或證據不足，"
            "並為使用的事實引用存在的 evidence_id；適用的數字計算請交由 compute_quant 決定性完成。"
        )
    else:
        user_text = (
            freshness_rules
            + phase_b_context + "\n\n"
            + f"幣種：{symbols[0]} vs {symbols[1]}\n問題：{question}\n\n"
            "請先辨識與問題相關的子問題，選擇至少 2 個能回答不同子問題且彼此互補的相關分析維度。"
            "Phase A 已預取兩幣種的核心資料（見上方摘要），請優先利用已有證據。"
            "只在需要更細粒度資料或 Phase A 缺失的維度時才呼叫額外工具。"
            "請在相同的相關維度下比較兩個幣種，依分析需要動態使用足夠的工具與證據，"
            "交叉比較一致訊號、背離訊號或證據不足，並為使用的事實引用存在的 evidence_id；"
            "凡適用的技術指標、百分位、報酬或相關係數等數字，均使用 compute_quant 決定性計算。"
        )

    messages = [{"role": "user", "content": [{"text": user_text}]}]
    tool_config = build_tool_config()

    forced_exit = False

    for turn in range(config.MAX_AGENT_TURNS):
        # 檢查時間預算
        elapsed = time.time() - loop_start
        if elapsed >= config.TIME_BUDGET_SECONDS:
            forced_exit = True
            evidence.log_execution_step(
                "agent_loop", "timeout", int(elapsed * 1000),
                note=f"Time budget exceeded at turn {turn + 1}"
            )
            break

        # Check if should force convergence (remaining < 20% of budget)
        if should_force_convergence(loop_start, config.TIME_BUDGET_SECONDS):
            # Inject convergence hint into messages
            convergence_msg = (
                "【時間預算即將耗盡】請立即整合已有證據，輸出最終分析結論。"
                "不要再呼叫新工具，直接根據已蒐集的資料完成分析。"
            )
            messages.append({"role": "user", "content": [{"text": convergence_msg}]})
            evidence.log_execution_step(
                "agent_loop", "force_convergence", int(elapsed * 1000),
                note=f"Remaining budget < 20% at turn {turn + 1}"
            )

        # 最後一輪：強制收斂，仍帶 tool_config（API 要求），但明確指示不再呼叫工具
        if turn == config.MAX_AGENT_TURNS - 1:
            messages.append({
                "role": "user",
                "content": [{"text": (
                    "【強制收斂指令】這是最後一輪，你不可以再呼叫任何工具。"
                    "請立刻根據目前已蒐集的所有資料，輸出你的最終分析結論。"
                    "用三段式結構：市場判斷、關鍵依據、信心說明。"
                )}]
            })
            try:
                response = call_bedrock(messages, tool_config, extra_system_text=question_type_prompt)
            except Exception as e:
                evidence.log_execution_step(
                    "agent_loop", "error", int((time.time() - loop_start) * 1000),
                    note=f"Forced convergence call failed: {type(e).__name__}: {str(e)}"
                )
                break

            if response:
                output_message = response.get("output", {}).get("message", {})
                if output_message:
                    messages.append(output_message)
            break

        # 呼叫 Bedrock (with question type prompt in system)
        try:
            response = call_bedrock(messages, tool_config, extra_system_text=question_type_prompt)
        except Exception as e:
            evidence.log_execution_step(
                "agent_loop", "error", int((time.time() - loop_start) * 1000),
                note=f"Bedrock call failed: {type(e).__name__}: {str(e)}"
            )
            break

        if response is None:
            break

        # 取出模型回應
        stop_reason = response.get("stopReason", "")
        output_message = response.get("output", {}).get("message", {})

        # 把模型回應加入對話歷史
        if output_message:
            messages.append(output_message)

        # 判斷 stopReason
        if stop_reason == "end_turn":
            # 模型認為分析完成
            break
        elif stop_reason == "tool_use":
            # 取出所有 toolUse 區塊
            tool_results = []
            for content_block in output_message.get("content", []):
                if "toolUse" in content_block:
                    tool_result = dispatch_tool_call(run_id, content_block["toolUse"])
                    tool_results.append({
                        "toolResult": tool_result
                    })

            # 把 toolResult 加回 messages
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
        else:
            # 其他 stopReason（如 max_tokens），視為結束
            break

    # 若因超輪次退出，記錄一下
    if not forced_exit and turn >= config.MAX_AGENT_TURNS - 1:
        evidence.log_execution_step(
            "agent_loop", "max_turns", int((time.time() - loop_start) * 1000),
            note=f"Reached MAX_AGENT_TURNS ({config.MAX_AGENT_TURNS})"
        )

    # Store final state in run context
    _run_context["total_elapsed_seconds"] = time.time() - loop_start
    _run_context["total_turns"] = turn + 1
    _run_context["series_count"] = len(_series_registry)

    return messages



EVIDENCE_INDEX_SOURCE_MAX_CHARS = 240
EVIDENCE_INDEX_CLAIM_MAX_CHARS = 320


def _bounded_evidence_index_text(value, max_chars):
    """將證據索引文字正規化並限制長度，避免摘要 prompt 膨脹。"""
    if value is None:
        return ""

    compact_text = " ".join(str(value).split())
    if len(compact_text) <= max_chars:
        return compact_text
    return compact_text[:max_chars - 1] + "…"


def _build_evidence_index():
    """依 evidence_list 順序建立去重且不含原始內容的精簡索引。"""
    index_lines = []
    seen_ids = set()

    for record in evidence.evidence_list:
        if not isinstance(record, dict):
            continue

        evidence_id = record.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            continue
        if evidence_id in seen_ids:
            continue

        seen_ids.add(evidence_id)
        index_lines.append(json.dumps({
            "evidence_id": evidence_id,
            "source": _bounded_evidence_index_text(
                record.get("source"), EVIDENCE_INDEX_SOURCE_MAX_CHARS
            ),
            "related_claim": _bounded_evidence_index_text(
                record.get("related_claim"), EVIDENCE_INDEX_CLAIM_MAX_CHARS
            ),
        }, ensure_ascii=False, separators=(",", ":")))

    if not index_lines:
        return "(無可用證據)"
    return "\n".join(index_lines)


def summarize_final_analysis(messages):
    """收尾用的第二次 Bedrock 呼叫（不提供工具）。

    明確要求模型依「市場判斷／關鍵依據／信心說明」三段式結構重新整理輸出。
    回傳：結構化的分析文字（Markdown 格式字串）。
    """
    evidence_index = _build_evidence_index()

    # 依題型附加專屬標記區塊，讓 report_schema 能解析 hypothesis/comparison 物件
    question_type = _run_context.get("question_type", "single_integration")
    if question_type == "hypothesis":
        type_specific_block = """
[HYPOTHESIS]
statement: （被檢驗的假設原句）
supporting: [（支持假設的證據要點，逗號分隔，每點含具體數字）]
opposing: [（反對假設的證據要點，逗號分隔，每點含具體數字）]
verdict_reason: （為什麼你做出這個判定，說明支持與反對兩方的權衡）
[/HYPOTHESIS]
"""
    elif question_type == "comparison":
        type_specific_block = """
[COMPARISON]
每個比較維度輸出一個 ROW 區塊：
[ROW]
dimension: （比較的維度名稱）
edge: （A 代表第一個幣種較強｜B 代表第二個幣種較強｜TIE 代表相當）
[/ROW]
when_prefer_a: （在什麼條件下第一個幣種更值得優先關注）
when_prefer_b: （在什麼條件下第二個幣種更值得優先關注）
[/COMPARISON]
"""
    else:
        type_specific_block = ""

    summarize_prompt = f"""根據以上所有蒐集到的資料與分析，請用以下三段式結構重新整理你的最終分析：

先在內容中明確列出實際使用的分析維度，並交叉比較這些維度的一致訊號、背離訊號或證據不足狀態。推理須遵循事實→推論→結論；來源矛盾時說明取捨依據。

## 可用證據索引（只能引用以下 ID）
{evidence_index}

引用規則：
- 每一項事實與每一條關鍵依據都必須引用索引中完全一致的 evidence_id。
- 只能逐字引用上述索引內的 ID，禁止杜撰、改寫或引用索引以外的 evidence_id。
- 有可用證據時，應從至少 2 個與題目相關且彼此互補的分析維度引用證據來支撐結論。
- 若少於 2 個互補且相關的維度有可用證據，必須明確說明證據不足並降低信心，不得捏造多維度結論。
- 若索引標示「(無可用證據)」，必須輸出低信心／證據不足的判斷，不得虛構事實、關鍵依據或 evidence_id。

## 市場判斷
（核心結論，清楚區分有 evidence_id 的事實、推論與結論）

## 關鍵依據
（每條依據標明對應的 evidence_id，說明該證據如何支撐判斷）

## 信心說明
（定性信心程度、已知限制、矛盾訊號取捨、推翻條件；只列與題目相關的省略或實際嘗試失敗的維度、原因及信心影響，不列無關且未嘗試的維度）

---

## 機器可讀區塊（必填，供前端視覺化使用）

在上述三段式內容之後，附加以下標記區塊。這些區塊的內容必須與上方三段式敘述一致，不得出現矛盾的結論或信心。
只描述你實際分析過的維度與實際偵測到的訊號，沒有就留空區塊，不要為了填滿而編造。

[VERDICT]
text: （一句話核心判斷，與「市場判斷」章節一致）
stance: （bullish｜bearish｜neutral｜mixed 四者之一）
confidence: （0 到 1 的小數，需與「信心說明」的定性描述一致，例如中等約 0.5、中高約 0.7）
invalidation: （什麼情況會推翻這個判斷，一句話）
[/VERDICT]

每個實際分析過的維度輸出一個區塊，欄位順序不可調換：
[DIM]
name: （維度名稱，例如 價格動能／槓桿結構／鏈上行為／情緒面／總經環境／DeFi生態）
state: （strong｜weak｜neutral｜na 四者之一；na 代表嘗試過但無可用資料）
headline: （這個維度的一句話結論，含具體數字）
evidence_ids: [ev_xxx, ev_yyy]
[/DIM]

每個偵測到的異常或背離訊號輸出一個區塊（沒有偵測到就完全不輸出 SIGNAL 區塊）：
[SIGNAL]
level: （red 代表強烈異常｜yellow 代表值得注意）
title: （訊號短標題）
detail: （為什麼值得注意，含具體數值與百分位）
evidence_ids: [ev_xxx]
[/SIGNAL]

[CHECKED_NORMAL]
- （已檢查但處於正常範圍的項目，一行一項，含數值。這是為了證明異常訊號是全面掃描後的結果）
[/CHECKED_NORMAL]

[COVERAGE]
pct: （題目相關資料的可用比例 0-100，或 null）
got: [（成功取得且品質可用的能力名稱）]
missing: [（嘗試過但失敗或無法取得的能力名稱）]
[/COVERAGE]

[WATCHLIST]
event: （後續值得觀察的事件名稱）
date: （YYYY-MM-DD，不確定就寫預估月份的第一天）
why: （為什麼這個事件會影響上述判斷）
[/WATCHLIST]
{type_specific_block}
請用繁體中文輸出，保持專業但易懂。不要輸出固定分母、覆蓋率或維度分數，也不要給出任何投資建議（不說買進、賣出、目標價、建議持有）。"""

    # 在對話歷史尾部加上摘要要求
    summarize_messages = messages.copy()
    summarize_messages.append({
        "role": "user",
        "content": [{"text": summarize_prompt}]
    })

    try:
        # 第二次呼叫仍需帶 toolConfig（因為 messages 中含有 toolUse/toolResult block）
        response = call_bedrock(summarize_messages, tool_config=build_tool_config())

        if response is None:
            return "（模型未能產生摘要回應）"

        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])

        # 取出文字內容
        text_parts = []
        for block in content_blocks:
            if "text" in block:
                text_parts.append(block["text"])

        if text_parts:
            return "\n".join(text_parts)
        else:
            return "（模型回應中無文字內容）"

    except Exception as e:
        return f"（摘要生成失敗：{type(e).__name__}: {str(e)}）"
