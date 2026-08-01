"""
agent.py — 多階段 Agent 架構（Planner + Sub-agent + Validator + Synthesis）

依照 agent-flexibility-output-contract.md 設計：
  1. Planner：動態拆題、選擇維度與工具、分配時間預算
  2. Sub-agent 研究執行器：最多 2-3 個專業角色，共用 Evidence Store
  3. Evidence Validator：硬性品質關卡
  4. Synthesis Agent：產出結構化 ReportModel JSON
  5. Renderer（在 report.py）：決定性渲染為 Markdown

核心原則：內部探索有彈性，外部輸出有契約；模型負責判斷，程式負責格式與驗證。
"""

import time
import json
import boto3
from botocore.exceptions import ClientError

import config
import evidence
from tools import price, news, onchain, quant, sentiment, macro
from tools import derivatives, prediction, defi, institutional

# ---- 工具分層定義 ----
# 核心層：幾乎每個題目都會用到
CORE_TOOLS = [
    "get_price_ohlcv", "compute_quant", "search_news",
    "get_onchain", "get_sentiment", "get_macro",
]
# 進階層：只在題目明確需要更深入的市場結構或機構視角時才選用
ADVANCED_TOOLS = [
    "get_derivatives", "get_prediction_market", "get_defi_data",
    "get_dev_activity", "get_orderbook_depth", "get_market_dominance",
    "get_cftc_cot", "get_sec_filings", "get_coin_metrics",
]

# 工具名稱與實際函式的對應表
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

# ---- 各階段時間預算（秒）----
PLANNER_BUDGET = int(config.TIME_BUDGET_SECONDS * 0.05)  # ~30s
RESEARCH_BUDGET = int(config.TIME_BUDGET_SECONDS * 0.55)  # ~330s
VALIDATION_BUDGET = int(config.TIME_BUDGET_SECONDS * 0.15)  # ~90s
SYNTHESIS_BUDGET = int(config.TIME_BUDGET_SECONDS * 0.20)  # ~120s
BUFFER_SECONDS = int(config.TIME_BUDGET_SECONDS * 0.05)  # ~30s 緩衝


# ============================================================
# Planner Prompt — 動態拆題、選擇維度與工具
# ============================================================
PLANNER_SYSTEM_PROMPT = """你是加密市場分析的規劃專家。你的職責是分析使用者的問題，
產出一個結構化的分析計畫（AnalysisPlan）。你不做分析本身，只做規劃。

## 輸出格式（必須嚴格輸出以下 JSON，不加其他文字）：
```json
{
  "question_type": "multi_source | hypothesis_validation | comparison",
  "time_horizon": "1d-7d | 7d-30d | 30d-90d | 90d+",
  "subquestions": ["子問題1", "子問題2", ...],
  "selected_dimensions": ["price_structure", "news_events", "onchain", "sentiment", "macro", "derivatives", "defi", ...],
  "tool_requests": [
    {"tool": "工具名稱", "params_hint": {"symbol": "BTC", ...}, "priority": "core|advanced"},
    ...
  ],
  "cross_validation_pairs": [["維度A", "維度B"], ...],
  "sub_agent_assignments": [
    {"role": "市場結構研究", "dimensions": ["price_structure", "derivatives"], "symbols": ["BTC"]},
    ...
  ]
}
```

## 判斷 question_type 的規則：
- 如果使用者提供了 2 個幣種，且問題涉及比較、對比、差異、相對表現 → "comparison"
- 如果問題要求驗證某個假設（如「是否過度擁擠」「是否被低估」）→ "hypothesis_validation"
- 其他（綜合分析、趨勢判讀、市場狀態描述）→ "multi_source"

## 工具分層邏輯（重要）：
核心層工具（幾乎每個題目都相關，優先使用）：
- get_price_ohlcv：價格走勢原始數據
- compute_quant：技術指標計算（數字一律由此工具產生）
- search_news：新聞與官方公告
- get_onchain：鏈上活躍度
- get_sentiment：市場恐懼貪婪指數
- get_macro：總經環境

進階層工具（只在題目明確需要時才選用 1-2 項，不要為了豐富度全部呼叫）：
- get_derivatives：衍生品（槓桿、資金費率、OI、DVOL）→ 適用於「槓桿擁擠」「多空比」類題目
- get_prediction_market：預測市場定價 → 適用於「事件機率」「市場預期」類題目
- get_defi_data：DeFi TVL/穩定幣 → 適用於「資金流」「DeFi 活躍度」類題目
- get_dev_activity：開發活躍度 → 適用於「基本面健康」「專案進展」類題目
- get_orderbook_depth：盤口深度 → 適用於「流動性」「滑價風險」類題目
- get_market_dominance：市值佔比 → 適用於「資金輪動」「避險情緒」類題目
- get_cftc_cot：CFTC 機構持倉 → 適用於「機構動向」（僅 BTC）
- get_sec_filings：SEC 監管文件 → 適用於「監管風險」「ETF」類題目
- get_coin_metrics：機構級鏈上指標 → 適用於「估值」「MVRV」類題目

## 比較分析特殊規則：
當 question_type 為 "comparison" 且有 2 個幣種時：
1. 必須為每個幣種分配對等的研究資源（Sub-agent 數量或工具呼叫次數對等）
2. tool_requests 中必須包含 compute_quant 帶 compare_symbol 參數來計算相關係數
3. sub_agent_assignments 中兩個幣種的 dimensions 應該對稱

## Sub-agent 分配規則：
- 最多分配 2-3 個 Sub-agent（不是每個維度都需要獨立 Sub-agent）
- 可以把相關維度合併到同一個 Sub-agent（如 price_structure + derivatives）
- 比較分析時：可以按幣種分配（每幣種一個 Sub-agent），或按維度分配但確保兩幣種都被覆蓋

## 你不得做的事：
- 不得決定最終報告的排版或格式
- 不得自行增加輸出欄位
- 不得強制規定「必須呼叫至少 N 種工具」— 依題目相關性動態決定
"""


# ============================================================
# Sub-agent Prompt — 專業研究執行器
# ============================================================
SUBAGENT_SYSTEM_PROMPT = """你是加密市場的專業研究員。你會收到一個研究任務分配，
包含你負責的維度、幣種、和要使用的工具。

## 你的職責：
1. 按照分配的工具清單依序呼叫工具蒐集資料
2. 每次呼叫工具時，related_claim 必填，說明這筆資料要用來檢驗什麼
3. 蒐集完成後，整理成結構化的 ResearchResult

## 輸出格式（蒐集完所有資料後，輸出以下 JSON）：
```json
{
  "dimension": "你負責的研究維度名稱",
  "summary": "一句話摘要你的發現",
  "facts": [
    {"statement": "直接從資料觀察到的事實", "evidence_ids": ["對應的 evidence_id"]}
  ],
  "signals": [
    {"direction": "bullish|bearish|neutral", "strength": "strong|moderate|weak", "description": "訊號描述"}
  ],
  "contradictions": [
    {"signal_a": "訊號A描述", "signal_b": "訊號B描述", "resolution": "你的取捨依據"}
  ],
  "limitations": ["資料不足或品質問題的說明"]
}
```

## 重要規則：
- 所有數字運算（技術指標、百分位、相關係數）必須透過 compute_quant 工具計算，不可心算
- 工具回傳錯誤時記錄為 limitation，不要停止研究
- 不要撰寫最終報告，只輸出 ResearchResult
- 不要給出投資建議（不說買進、賣出、目標價）
"""


# ============================================================
# Synthesis Prompt — 產出 ReportModel JSON
# ============================================================
SYNTHESIS_SYSTEM_PROMPT = """你是加密市場分析的綜合研判專家。你會收到多個研究維度的結果，
你的職責是綜合所有資料產出一個結構化的 ReportModel。

## 輸出格式（必須嚴格輸出以下 JSON，不加其他文字）：
```json
{
  "market_state": {
    "regime": "用一句話描述當前市場狀態（如：低波動盤整、槓桿堆積、趨勢延續等）",
    "confidence": "low | medium | high",
    "time_horizon": "分析涵蓋的時間範圍"
  },
  "key_findings": [
    {
      "layer": "fact | inference | conclusion",
      "statement": "發現描述",
      "evidence_ids": ["支撐此發現的 evidence_id"],
      "importance": "high | medium | low"
    }
  ],
  "supporting_signals": [
    {"direction": "bullish|bearish|neutral", "description": "支持主要判斷的訊號", "evidence_ids": []}
  ],
  "contradicting_signals": [
    {"direction": "bullish|bearish|neutral", "description": "與主要判斷矛盾的訊號", "evidence_ids": [], "resolution": "取捨依據"}
  ],
  "catalysts": ["可能改變現狀的觸發事件"],
  "risks": ["主要風險因子"],
  "invalidation_conditions": ["什麼情況會推翻你的結論"],
  "watch_items": ["短期值得關注的指標或事件"],
  "limitations": ["資料不足、品質問題、或分析方法的限制"],
  "evidence_ids": ["本報告引用的所有 evidence_id 完整列表"]
}
```

## 綜合研判規則：
1. 明確區分事實（有 evidence_id 支撐）→ 推論（說明邏輯）→ 結論（標信心程度）
2. 訊號矛盾時：明寫矛盾內容與取捨依據，不可忽略反方證據
3. 資料缺失時：列入 limitations，降低 confidence，不硬給結論
4. 跨來源交叉驗證：不同維度的訊號是否一致？背離本身就是有價值的發現
5. confidence 只用 low/medium/high 三個值，不可自創百分比
6. 不輸出買進、賣出、配置比例、目標價或任何投資建議
7. 每個 key_finding 的 evidence_ids 必須引用真實存在的 evidence_id
"""


# ============================================================
# 工具規格定義（與原版相同，不修改工具本身）
# ============================================================
def build_tool_config():
    """組出 Bedrock Converse API 的 toolConfig JSON。"""
    tools = [
        {
            "toolSpec": {
                "name": "get_price_ohlcv",
                "description": "取得指定幣種在指定期間的日線 OHLCV（開高低收量）資料。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "幣種代號"},
                    "start_date": {"type": "string", "description": "起始日期 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "結束日期 YYYY-MM-DD"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["symbol", "start_date", "end_date", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "search_news",
                "description": "查詢指定幣種的近期新聞、官方公告與監管消息。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "幣種代號"},
                    "lookback_days": {"type": "integer", "description": "往回查幾天"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"},
                    "keywords": {"type": "string", "description": "額外搜尋關鍵字（選填）"}
                }, "required": ["symbol", "lookback_days", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_onchain",
                "description": "取得指定幣種的鏈上活躍度指標。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "幣種代號"},
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "要查詢的指標清單"},
                    "lookback_days": {"type": "integer", "description": "往回查幾天"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["symbol", "metrics", "lookback_days", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "compute_quant",
                "description": "計算技術指標（ATR%、布林帶寬、ADX、成交量 Z-score、已實現波動率、相關係數等）。所有數字必須由此工具計算。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "幣種代號"},
                    "features": {"type": "array", "items": {"type": "string"}, "description": "要計算的指標清單"},
                    "window": {"type": "integer", "description": "計算窗口天數"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"},
                    "compare_symbol": {"type": "string", "description": "比較幣種（計算相關係數時使用，選填）"}
                }, "required": ["symbol", "features", "window", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_sentiment",
                "description": "取得市場恐懼與貪婪指數的當前值與近期走勢。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"},
                    "lookback_days": {"type": "integer", "description": "往回查幾天，預設 30"}
                }, "required": ["related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_macro",
                "description": "取得總體經濟指標與近期重要總經事件排程。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "indicators": {"type": "array", "items": {"type": "string"}, "description": "總經指標清單"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"},
                    "lookback_days": {"type": "integer", "description": "往回查幾天，預設 90"}
                }, "required": ["indicators", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_derivatives",
                "description": "取得衍生品市場資料：資金費率、未平倉量、清算、隱含波動率、大戶多空比。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "幣種代號"},
                    "source": {"type": "string", "description": "資料來源：hyperliquid | binance_futures | deribit"},
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "要取得的指標"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["symbol", "source", "metrics", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_prediction_market",
                "description": "查詢 Polymarket 預測市場上加密相關事件的市場定價。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "keywords": {"type": "string", "description": "搜尋關鍵字"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["keywords", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_defi_data",
                "description": "取得 DeFi TVL 與穩定幣供給量資料。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "指標：tvl / stablecoin_supply"},
                    "chain": {"type": "string", "description": "指定鏈或 all"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["metrics", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_dev_activity",
                "description": "取得幣種專案的 GitHub 開發活躍度。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "幣種代號"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["symbol", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_orderbook_depth",
                "description": "取得 Binance Spot 盤口深度快照。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "幣種代號"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["symbol", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_market_dominance",
                "description": "取得 BTC 及各幣種的市值佔比。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_cftc_cot",
                "description": "取得 CFTC COT 報告中 CME Bitcoin 期貨的機構持倉數據（僅 BTC）。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "目前僅支援 BTC"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["symbol", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_sec_filings",
                "description": "搜尋 SEC EDGAR 近期加密相關監管文件。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "keywords": {"type": "string", "description": "搜尋關鍵字"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["keywords", "related_claim"]}}
            }
        },
        {
            "toolSpec": {
                "name": "get_coin_metrics",
                "description": "取得 Coin Metrics Community 的機構級鏈上/市場指標。",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "symbol": {"type": "string", "description": "幣種代號"},
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "指標列表"},
                    "related_claim": {"type": "string", "description": "這筆資料要用來檢驗什麼判斷（必填）"}
                }, "required": ["symbol", "metrics", "related_claim"]}}
            }
        },
    ]
    return {"tools": tools}


# ============================================================
# Bedrock 呼叫層
# ============================================================
def call_bedrock(messages, system_prompt, tool_config=None):
    """呼叫 Bedrock Converse API 一次。處理 ThrottlingException。"""
    client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)

    kwargs = {
        "modelId": config.BEDROCK_MODEL_ID,
        "messages": messages,
        "system": [{"text": system_prompt}],
    }
    if tool_config:
        kwargs["toolConfig"] = tool_config

    for attempt in range(2):
        try:
            response = client.converse(**kwargs)
            return response
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ThrottlingException" and attempt == 0:
                time.sleep(2)
                continue
            else:
                raise

    return None


# ============================================================
# 工具分派（與原版相同邏輯）
# ============================================================
def dispatch_tool_call(run_id, tool_use_block):
    """根據模型指定的工具名稱執行對應函式，記錄證據。
    回傳 toolResult 區塊（僅含 summary + evidence_id）。"""
    tool_name = tool_use_block["name"]
    tool_input = tool_use_block["input"]
    tool_use_id = tool_use_block["toolUseId"]

    start_time = time.time()

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
        result = func(**tool_input)
        elapsed_ms = int((time.time() - start_time) * 1000)

        if isinstance(result, dict) and "error" in result:
            evidence.log_execution_step(tool_name, "error", elapsed_ms, note=result["error"])
            return {
                "toolUseId": tool_use_id,
                "content": [{"text": json.dumps({"error": result["error"]})}],
                "status": "error",
            }

        related_claim = tool_input.get("related_claim", "")
        evidence_id = evidence.log_evidence(run_id, tool_name, related_claim, result)

        if isinstance(evidence_id, dict) and "error" in evidence_id:
            evidence.log_execution_step(tool_name, "warning", elapsed_ms, note=evidence_id["error"])
            evidence_id = None

        evidence.log_execution_step(tool_name, "success", elapsed_ms, evidence_id=evidence_id)

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


# ============================================================
# 階段 1：Planner — 動態拆題
# ============================================================
def run_planner(symbols, question, deadline):
    """呼叫 Planner 模型產出 AnalysisPlan JSON。

    回傳：AnalysisPlan dict，或 fallback plan（若模型失敗）。
    """
    evidence.log_execution_step("planner", "start", 0, note="Planning phase started")
    start_time = time.time()

    # 組裝 Planner 的使用者訊息
    symbols_str = " vs ".join(symbols) if len(symbols) > 1 else symbols[0]
    user_text = (
        f"幣種：{symbols_str}\n"
        f"問題：{question}\n"
        f"幣種數量：{len(symbols)}\n\n"
        f"請分析這個問題並產出 AnalysisPlan JSON。"
    )

    messages = [{"role": "user", "content": [{"text": user_text}]}]

    try:
        response = call_bedrock(messages, PLANNER_SYSTEM_PROMPT)
        elapsed_ms = int((time.time() - start_time) * 1000)

        if response is None:
            evidence.log_execution_step("planner", "error", elapsed_ms, note="No response from Bedrock")
            return _fallback_plan(symbols, question)

        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])

        # 從回應中提取 JSON
        plan_json = _extract_json_from_response(content_blocks)

        if plan_json:
            # 驗證並修正 plan
            plan = _validate_and_fix_plan(plan_json, symbols, question)
            evidence.log_execution_step("planner", "success", elapsed_ms,
                                        note=f"question_type={plan.get('question_type')}")
            return plan
        else:
            evidence.log_execution_step("planner", "error", elapsed_ms, note="Failed to extract JSON")
            return _fallback_plan(symbols, question)

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step("planner", "error", elapsed_ms,
                                    note=f"Planner failed: {type(e).__name__}: {str(e)}")
        return _fallback_plan(symbols, question)


def _extract_json_from_response(content_blocks):
    """從模型回應的 content blocks 中提取 JSON 物件。"""
    import re
    for block in content_blocks:
        if "text" in block:
            text = block["text"]
            # 嘗試找 code block 中的 JSON
            json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1).strip())
                except json.JSONDecodeError:
                    pass
            # 嘗試直接解析整段文字
            try:
                return json.loads(text.strip())
            except json.JSONDecodeError:
                pass
            # 嘗試找第一個 { 到最後一個 }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
    return None


def _validate_and_fix_plan(plan, symbols, question):
    """驗證 AnalysisPlan 並修正常見問題。"""
    # 確保 question_type 存在且合法
    valid_types = ["multi_source", "hypothesis_validation", "comparison"]
    if plan.get("question_type") not in valid_types:
        # 根據幣種數量推斷
        if len(symbols) > 1:
            plan["question_type"] = "comparison"
        else:
            plan["question_type"] = "multi_source"

    # 比較分析強制規則：2 個幣種時必須是 comparison
    if len(symbols) > 1:
        plan["question_type"] = "comparison"

    # 確保必要欄位存在
    plan.setdefault("time_horizon", "7d-30d")
    plan.setdefault("subquestions", [])
    plan.setdefault("selected_dimensions", ["price_structure", "news_events"])
    plan.setdefault("tool_requests", [])
    plan.setdefault("cross_validation_pairs", [])
    plan.setdefault("sub_agent_assignments", [])

    # 比較分析時確保有 correlation 計算
    if plan["question_type"] == "comparison" and len(symbols) == 2:
        _ensure_correlation_tool(plan, symbols)

    # 確保 Sub-agent 數量不超過 3
    if len(plan["sub_agent_assignments"]) > 3:
        plan["sub_agent_assignments"] = plan["sub_agent_assignments"][:3]

    # 若 Sub-agent 分配為空，產生預設分配
    if not plan["sub_agent_assignments"]:
        plan["sub_agent_assignments"] = _generate_default_assignments(plan, symbols)

    return plan


def _ensure_correlation_tool(plan, symbols):
    """確保比較分析計畫中包含 compute_quant + compare_symbol 呼叫。"""
    has_correlation = False
    for req in plan.get("tool_requests", []):
        if req.get("tool") == "compute_quant":
            hints = req.get("params_hint", {})
            if hints.get("compare_symbol") or "correlation" in str(hints.get("features", [])):
                has_correlation = True
                break

    if not has_correlation:
        plan["tool_requests"].append({
            "tool": "compute_quant",
            "params_hint": {
                "symbol": symbols[0],
                "compare_symbol": symbols[1],
                "features": ["correlation", "atr_pct", "realized_vol"],
                "window": 30
            },
            "priority": "core"
        })


def _generate_default_assignments(plan, symbols):
    """根據 plan 的 selected_dimensions 產生預設 Sub-agent 分配。"""
    if plan["question_type"] == "comparison" and len(symbols) == 2:
        # 比較分析：每幣種一個 Sub-agent，確保對等
        dims = plan.get("selected_dimensions", ["price_structure", "news_events", "onchain"])
        return [
            {"role": f"{symbols[0]} 研究", "dimensions": dims, "symbols": [symbols[0]]},
            {"role": f"{symbols[1]} 研究", "dimensions": dims, "symbols": [symbols[1]]},
        ]
    else:
        # 單幣種：依維度分組
        all_dims = plan.get("selected_dimensions", ["price_structure", "news_events", "onchain", "sentiment"])
        # 分成最多 2 組
        mid = len(all_dims) // 2
        group1 = all_dims[:max(mid, 1)]
        group2 = all_dims[max(mid, 1):]
        assignments = [
            {"role": "市場結構與技術研究", "dimensions": group1, "symbols": symbols},
        ]
        if group2:
            assignments.append(
                {"role": "基本面與情緒研究", "dimensions": group2, "symbols": symbols}
            )
        return assignments


def _fallback_plan(symbols, question):
    """當 Planner 失敗時使用的保守 fallback 計畫。"""
    is_comparison = len(symbols) > 1
    question_type = "comparison" if is_comparison else "multi_source"

    base_dims = ["price_structure", "news_events", "onchain", "sentiment", "macro"]
    base_tools = [
        {"tool": "get_price_ohlcv", "params_hint": {"symbol": symbols[0]}, "priority": "core"},
        {"tool": "compute_quant", "params_hint": {"symbol": symbols[0]}, "priority": "core"},
        {"tool": "search_news", "params_hint": {"symbol": symbols[0]}, "priority": "core"},
        {"tool": "get_onchain", "params_hint": {"symbol": symbols[0]}, "priority": "core"},
        {"tool": "get_sentiment", "params_hint": {}, "priority": "core"},
        {"tool": "get_macro", "params_hint": {}, "priority": "core"},
    ]

    if is_comparison:
        base_tools.extend([
            {"tool": "get_price_ohlcv", "params_hint": {"symbol": symbols[1]}, "priority": "core"},
            {"tool": "compute_quant", "params_hint": {"symbol": symbols[1]}, "priority": "core"},
            {"tool": "compute_quant", "params_hint": {
                "symbol": symbols[0], "compare_symbol": symbols[1],
                "features": ["correlation"]
            }, "priority": "core"},
            {"tool": "search_news", "params_hint": {"symbol": symbols[1]}, "priority": "core"},
            {"tool": "get_onchain", "params_hint": {"symbol": symbols[1]}, "priority": "core"},
        ])

    assignments = _generate_default_assignments(
        {"question_type": question_type, "selected_dimensions": base_dims}, symbols
    )

    return {
        "question_type": question_type,
        "time_horizon": "7d-30d",
        "subquestions": [question],
        "selected_dimensions": base_dims,
        "tool_requests": base_tools,
        "cross_validation_pairs": [["price_structure", "onchain"], ["sentiment", "news_events"]],
        "sub_agent_assignments": assignments,
    }


# ============================================================
# 階段 2：Sub-agent 研究執行器
# ============================================================
def run_sub_agent(run_id, assignment, plan, deadline):
    """執行一個 Sub-agent 的研究任務。

    使用 Bedrock Converse + 工具呼叫迴圈蒐集資料，
    最終產出 ResearchResult JSON。

    Args:
        run_id: 本次執行 ID
        assignment: {"role": str, "dimensions": list, "symbols": list}
        plan: 完整的 AnalysisPlan
        deadline: 絕對時間戳（time.time() 格式），超過就停

    回傳：ResearchResult dict
    """
    role = assignment.get("role", "研究員")
    dimensions = assignment.get("dimensions", [])
    symbols = assignment.get("symbols", [])

    evidence.log_execution_step(
        f"sub_agent_{role}", "start", 0,
        note=f"dims={dimensions}, symbols={symbols}"
    )
    start_time = time.time()

    # 組裝 Sub-agent 的指示
    symbols_str = ", ".join(symbols)
    dims_str = ", ".join(dimensions)

    # 根據 plan 的 tool_requests 篩選此 Sub-agent 該用的工具
    relevant_tools = _select_tools_for_assignment(assignment, plan)
    tools_str = ", ".join(relevant_tools) if relevant_tools else "依研究需要自行選擇"

    user_text = (
        f"## 研究任務分配\n"
        f"- 角色：{role}\n"
        f"- 負責維度：{dims_str}\n"
        f"- 目標幣種：{symbols_str}\n"
        f"- 問題背景：{plan.get('subquestions', [''])[0] if plan.get('subquestions') else ''}\n"
        f"- 題型：{plan.get('question_type', 'multi_source')}\n"
        f"- 時間範圍：{plan.get('time_horizon', '7d-30d')}\n"
        f"- 建議使用工具：{tools_str}\n\n"
        f"請開始蒐集資料，完成後輸出 ResearchResult JSON。"
    )

    messages = [{"role": "user", "content": [{"text": user_text}]}]
    tool_config = build_tool_config()

    max_turns = config.MAX_SUB_AGENT_TURNS  # Sub-agent 每個最多 6 輪工具呼叫

    for turn in range(max_turns):
        # 檢查全流程 deadline
        if time.time() >= deadline:
            evidence.log_execution_step(
                f"sub_agent_{role}", "timeout",
                int((time.time() - start_time) * 1000),
                note=f"Deadline reached at turn {turn + 1}"
            )
            break

        try:
            response = call_bedrock(messages, SUBAGENT_SYSTEM_PROMPT, tool_config)
        except Exception as e:
            evidence.log_execution_step(
                f"sub_agent_{role}", "error",
                int((time.time() - start_time) * 1000),
                note=f"Bedrock call failed: {type(e).__name__}: {str(e)}"
            )
            break

        if response is None:
            break

        stop_reason = response.get("stopReason", "")
        output_message = response.get("output", {}).get("message", {})

        if output_message:
            messages.append(output_message)

        if stop_reason == "end_turn":
            break
        elif stop_reason == "tool_use":
            tool_results = []
            for content_block in output_message.get("content", []):
                if "toolUse" in content_block:
                    tool_result = dispatch_tool_call(run_id, content_block["toolUse"])
                    tool_results.append({"toolResult": tool_result})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
        else:
            break

    # 從最後的模型回應中提取 ResearchResult
    elapsed_ms = int((time.time() - start_time) * 1000)
    research_result = _extract_research_result(messages, role, dimensions)
    evidence.log_execution_step(
        f"sub_agent_{role}", "success", elapsed_ms,
        note=f"facts={len(research_result.get('facts', []))}"
    )
    return research_result


def _select_tools_for_assignment(assignment, plan):
    """根據 Sub-agent 的維度和 plan 的 tool_requests，篩選相關工具。"""
    dimensions = set(assignment.get("dimensions", []))
    symbols = set(assignment.get("symbols", []))

    # 維度 → 工具名對應
    dim_tool_map = {
        "price_structure": ["get_price_ohlcv", "compute_quant", "get_orderbook_depth"],
        "news_events": ["search_news", "get_sec_filings"],
        "onchain": ["get_onchain", "get_coin_metrics"],
        "sentiment": ["get_sentiment", "get_prediction_market"],
        "macro": ["get_macro"],
        "derivatives": ["get_derivatives"],
        "defi": ["get_defi_data"],
        "dev_activity": ["get_dev_activity"],
        "dominance": ["get_market_dominance"],
        "institutional": ["get_cftc_cot", "get_sec_filings", "get_coin_metrics"],
    }

    relevant = set()
    for dim in dimensions:
        if dim in dim_tool_map:
            relevant.update(dim_tool_map[dim])

    # 也從 plan.tool_requests 中加入與此 Sub-agent 幣種相關的工具
    for req in plan.get("tool_requests", []):
        tool_name = req.get("tool", "")
        hints = req.get("params_hint", {})
        req_symbol = hints.get("symbol", "")
        if req_symbol in symbols or not req_symbol:
            relevant.add(tool_name)

    return sorted(relevant)


def _extract_research_result(messages, role, dimensions):
    """從 Sub-agent 對話歷史中提取 ResearchResult JSON。"""
    # 從最後一則 assistant 訊息中找 JSON
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content_blocks = msg.get("content", [])
            result = _extract_json_from_response(content_blocks)
            if result and "facts" in result:
                # 確保有 dimension 欄位
                result.setdefault("dimension", dimensions[0] if dimensions else role)
                result.setdefault("summary", "")
                result.setdefault("facts", [])
                result.setdefault("signals", [])
                result.setdefault("contradictions", [])
                result.setdefault("limitations", [])
                return result

    # 若無法提取 JSON，嘗試從文字中擷取有意義資訊
    fallback_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            for block in msg.get("content", []):
                if "text" in block:
                    fallback_text = block["text"]
                    break
            if fallback_text:
                break

    return {
        "dimension": dimensions[0] if dimensions else role,
        "summary": fallback_text[:200] if fallback_text else f"（{role} 未能產出結構化結果）",
        "facts": [],
        "signals": [],
        "contradictions": [],
        "limitations": [f"{role} 未能產出 ResearchResult JSON 格式"]
    }


# ============================================================
# 階段 3：Evidence Validator
# ============================================================
def validate_research(research_results, evidence_list):
    """驗證所有 ResearchResult 的品質。

    檢查項目（依 4.3 節）：
    - evidence ID 是否存在且不重複
    - 每項事實是否至少引用一筆有效證據
    - 是否含投資建議語句
    - 記錄矛盾與缺口

    回傳：(validated_results, validation_issues)
    """
    evidence.log_execution_step("validator", "start", 0, note="Validation phase started")
    start_time = time.time()

    issues = []
    valid_evidence_ids = {r.get("evidence_id") for r in evidence_list}

    for result in research_results:
        dim = result.get("dimension", "unknown")

        # 檢查 facts 的 evidence_ids 是否有效
        for fact in result.get("facts", []):
            fact_eids = fact.get("evidence_ids", [])
            if not fact_eids:
                issues.append(f"[{dim}] fact 缺少 evidence_id: {fact.get('statement', '')[:50]}")
            else:
                for eid in fact_eids:
                    if eid and eid not in valid_evidence_ids:
                        issues.append(f"[{dim}] 無效 evidence_id: {eid}")

        # 檢查投資建議語句
        forbidden = ["買進", "賣出", "目標價", "建議持有", "建議買入", "建議賣出"]
        text_to_check = json.dumps(result, ensure_ascii=False)
        for phrase in forbidden:
            if phrase in text_to_check:
                issues.append(f"[{dim}] 含投資建議語句：{phrase}")

    elapsed_ms = int((time.time() - start_time) * 1000)
    status = "success" if not issues else "warning"
    evidence.log_execution_step(
        "validator", status, elapsed_ms,
        note=f"issues={len(issues)}"
    )

    return research_results, issues


# ============================================================
# 階段 4：Synthesis Agent — 產出 ReportModel
# ============================================================
def run_synthesis(run_id, plan, research_results, validation_issues, deadline):
    """呼叫 Synthesis 模型綜合所有研究結果，產出 ReportModel JSON。

    回傳：ReportModel dict
    """
    evidence.log_execution_step("synthesis", "start", 0, note="Synthesis phase started")
    start_time = time.time()

    # 組裝 Synthesis 的輸入
    research_summary = json.dumps(research_results, ensure_ascii=False, indent=2)

    # 收集所有有效 evidence_ids
    all_evidence_ids = [r.get("evidence_id") for r in evidence.evidence_list]

    user_text = (
        f"## 分析計畫摘要\n"
        f"- 題型：{plan.get('question_type')}\n"
        f"- 時間範圍：{plan.get('time_horizon')}\n"
        f"- 子問題：{json.dumps(plan.get('subquestions', []), ensure_ascii=False)}\n"
        f"- 分析維度：{json.dumps(plan.get('selected_dimensions', []), ensure_ascii=False)}\n\n"
        f"## 研究結果\n```json\n{research_summary}\n```\n\n"
        f"## 可用的 evidence_ids\n{json.dumps(all_evidence_ids, ensure_ascii=False)}\n\n"
        f"## 驗證問題\n{json.dumps(validation_issues, ensure_ascii=False)}\n\n"
        f"請綜合以上資料，產出 ReportModel JSON。"
    )

    messages = [{"role": "user", "content": [{"text": user_text}]}]

    try:
        # 檢查 deadline
        if time.time() >= deadline:
            evidence.log_execution_step("synthesis", "timeout",
                                        int((time.time() - start_time) * 1000))
            return _fallback_report_model(plan, research_results, validation_issues)

        response = call_bedrock(messages, SYNTHESIS_SYSTEM_PROMPT)
        elapsed_ms = int((time.time() - start_time) * 1000)

        if response is None:
            evidence.log_execution_step("synthesis", "error", elapsed_ms, note="No response")
            return _fallback_report_model(plan, research_results, validation_issues)

        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])

        report_model = _extract_json_from_response(content_blocks)

        if report_model and "market_state" in report_model:
            # 驗證 ReportModel 結構
            report_model = _validate_report_model(report_model)
            evidence.log_execution_step("synthesis", "success", elapsed_ms,
                                        note=f"confidence={report_model.get('market_state', {}).get('confidence')}")
            return report_model
        else:
            evidence.log_execution_step("synthesis", "error", elapsed_ms,
                                        note="Failed to extract ReportModel")
            return _fallback_report_model(plan, research_results, validation_issues)

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        evidence.log_execution_step("synthesis", "error", elapsed_ms,
                                    note=f"Synthesis failed: {type(e).__name__}: {str(e)}")
        return _fallback_report_model(plan, research_results, validation_issues)


def _validate_report_model(model):
    """驗證並修正 ReportModel 結構，確保所有必要欄位存在。"""
    # 確保 market_state 結構完整
    ms = model.setdefault("market_state", {})
    ms.setdefault("regime", "無法判斷")
    if ms.get("confidence") not in ("low", "medium", "high"):
        ms["confidence"] = "low"
    ms.setdefault("time_horizon", "7d-30d")

    # 確保列表欄位存在
    model.setdefault("key_findings", [])
    model.setdefault("supporting_signals", [])
    model.setdefault("contradicting_signals", [])
    model.setdefault("catalysts", [])
    model.setdefault("risks", [])
    model.setdefault("invalidation_conditions", [])
    model.setdefault("watch_items", [])
    model.setdefault("limitations", [])
    model.setdefault("evidence_ids", [])

    # 確保 key_findings 中每項有正確的 layer 值
    valid_layers = ("fact", "inference", "conclusion")
    for finding in model["key_findings"]:
        if finding.get("layer") not in valid_layers:
            finding["layer"] = "inference"
        finding.setdefault("statement", "")
        finding.setdefault("evidence_ids", [])
        finding.setdefault("importance", "medium")

    return model


def _fallback_report_model(plan, research_results, validation_issues):
    """當 Synthesis 失敗時，根據已有資料產出最低限度的 ReportModel。"""
    # 收集所有 facts
    all_facts = []
    all_limitations = list(validation_issues)
    all_signals = []

    for result in research_results:
        for fact in result.get("facts", []):
            all_facts.append({
                "layer": "fact",
                "statement": fact.get("statement", ""),
                "evidence_ids": fact.get("evidence_ids", []),
                "importance": "medium"
            })
        for signal in result.get("signals", []):
            all_signals.append(signal)
        all_limitations.extend(result.get("limitations", []))

    all_limitations.append("Synthesis Agent 未能正常產出結構化結果，此為保守降級報告")

    return {
        "market_state": {
            "regime": "無法完整判斷（降級模式）",
            "confidence": "low",
            "time_horizon": plan.get("time_horizon", "7d-30d")
        },
        "key_findings": all_facts[:10],
        "supporting_signals": [s for s in all_signals if s.get("direction") != "bearish"][:5],
        "contradicting_signals": [s for s in all_signals if s.get("direction") == "bearish"][:5],
        "catalysts": [],
        "risks": ["分析流程未完整完成"],
        "invalidation_conditions": ["取得更完整的資料後應重新分析"],
        "watch_items": [],
        "limitations": all_limitations,
        "evidence_ids": [r.get("evidence_id") for r in evidence.evidence_list]
    }


# ============================================================
# 主入口：多階段 Agent 迴圈
# ============================================================
def run_agent_loop(run_id, symbols, question):
    """多階段 Agent 主流程。

    階段：Planner → Sub-agents → Validator → Synthesis
    受全流程 deadline 控制（TIME_BUDGET_SECONDS）。

    回傳：ReportModel dict（供 report.py 渲染）。
    """
    loop_start = time.time()
    deadline = loop_start + config.TIME_BUDGET_SECONDS - BUFFER_SECONDS

    evidence.log_execution_step(
        "agent_pipeline", "start", 0,
        note=f"symbols={symbols}, budget={config.TIME_BUDGET_SECONDS}s"
    )

    # ---- 階段 1：Planner ----
    plan = run_planner(symbols, question, deadline)

    # ---- 階段 2：Sub-agent 研究執行 ----
    research_results = []
    assignments = plan.get("sub_agent_assignments", [])

    # 限制最多 3 個 Sub-agent
    assignments = assignments[:3]

    for assignment in assignments:
        # 每次進入 Sub-agent 前檢查 deadline
        if time.time() >= deadline:
            evidence.log_execution_step(
                "agent_pipeline", "timeout",
                int((time.time() - loop_start) * 1000),
                note="Deadline reached before all sub-agents completed"
            )
            break

        result = run_sub_agent(run_id, assignment, plan, deadline)
        research_results.append(result)

    # ---- 階段 3：Evidence Validator ----
    if time.time() < deadline:
        validated_results, validation_issues = validate_research(
            research_results, evidence.evidence_list
        )
    else:
        validated_results = research_results
        validation_issues = ["驗證階段因時間不足而跳過"]

    # ---- 階段 4：Synthesis ----
    if time.time() < deadline:
        report_model = run_synthesis(
            run_id, plan, validated_results, validation_issues, deadline
        )
    else:
        report_model = _fallback_report_model(plan, research_results, validation_issues)
        evidence.log_execution_step(
            "synthesis", "skipped",
            int((time.time() - loop_start) * 1000),
            note="Deadline reached, using fallback report"
        )

    # 記錄總耗時
    total_elapsed = int((time.time() - loop_start) * 1000)
    evidence.log_execution_step(
        "agent_pipeline", "complete", total_elapsed,
        note=f"stages_completed, evidence_count={len(evidence.evidence_list)}"
    )

    return report_model
