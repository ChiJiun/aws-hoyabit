"""
agent.py — Agent 主迴圈與工具規格

這是整個系統的核心。run_agent_loop 維持「呼叫模型 → 判斷模型是否要用工具
→ 分派到對應工具 → 把結果餵回模型」的循環，直到模型認為證據足夠。
"""

import time
import json
import boto3
from botocore.exceptions import ClientError

import config
import evidence
from tools import price, news, onchain, quant, sentiment, macro

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
}


SYSTEM_PROMPT = """你是加密市場分析助理。使用者會給你一個幣種和一個問題，
你要蒐集多方資料，產出一份有證據支撐的分析。你不做投資建議
（不說買進、賣出、目標價），你只做資訊的整理與判斷。

工作步驟：
1. 先想清楚：要回答這個問題，需要哪幾類資料？至少涵蓋價格、新聞、鏈上三類。
2. 呼叫工具取得資料。每次呼叫工具時，related_claim 欄位必填，說明「這筆資料
   要用來檢驗什麼」。這能逼你先想好再查。
3. 拿到資料後，把你的分析拆成三個層次，且要標清楚：
   - 事實(fact)：資料直接顯示的，例如「14 日 ATR% 為 2.1%」
   - 推論(inference)：由事實推導的，例如「波動率處於歷史低位」
   - 結論(conclusion)：綜合判斷，例如「短期偏向盤整，但有事件風險」
4. 誠實說明信心與限制：
   - 哪些資料你沒拿到？
   - 有沒有互相矛盾的訊號？如果有，說明你怎麼取捨。
   - 什麼情況會推翻你的結論？
   資料不足時就說「無法給出高信心判斷」，不要硬湊結論。

重要：所有數字運算（技術指標、百分位、相關係數）都要透過 compute_quant
工具計算，不要自己心算。
"""


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
                "description": "取得指定幣種在指定期間的日線 OHLCV（開高低收量）資料。用於觀察價格走勢、計算技術指標的原始數據。",
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
                "description": "查詢指定幣種的近期新聞、官方公告與監管消息。用於了解基本面事件與市場敘事。",
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
    ]

    return {"tools": tools}


def call_bedrock(messages, tool_config=None):
    """呼叫 Bedrock Converse API 一次。

    處理 ThrottlingException（等待 2 秒重試一次）。
    回傳：API 的完整回應 dict。
    """
    client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)

    kwargs = {
        "modelId": config.BEDROCK_MODEL_ID,
        "messages": messages,
        "system": [{"text": SYSTEM_PROMPT}],
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
            "toolResultId": tool_use_id,
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
                "toolResultId": tool_use_id,
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

        # 組裝精簡的 toolResult（不含 raw，避免 context 膨脹）
        tool_result_content = {
            "summary": result.get("summary", "No summary available"),
            "evidence_id": evidence_id,
        }

        return {
            "toolResultId": tool_use_id,
            "content": [{"text": json.dumps(tool_result_content, ensure_ascii=False)}],
            "status": "success",
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_msg = f"[{tool_name}] {type(e).__name__}: {str(e)}"
        evidence.log_execution_step(tool_name, "error", elapsed_ms, note=error_msg)
        return {
            "toolResultId": tool_use_id,
            "content": [{"text": json.dumps({"error": error_msg})}],
            "status": "error",
        }


def run_agent_loop(run_id, symbols, question):
    """系統核心。維持 Agent 的對話迴圈直到模型完成分析。

    受 MAX_AGENT_TURNS 與 TIME_BUDGET_SECONDS 雙重限制。
    回傳：messages 陣列（完整對話歷史）。
    """
    # 組裝初始 user 訊息
    if len(symbols) == 1:
        user_text = f"幣種：{symbols[0]}\n問題：{question}"
    else:
        user_text = f"幣種：{symbols[0]} vs {symbols[1]}\n問題：{question}"

    messages = [{"role": "user", "content": [{"text": user_text}]}]
    tool_config = build_tool_config()

    loop_start = time.time()
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

        # 呼叫 Bedrock
        try:
            response = call_bedrock(messages, tool_config)
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

    return messages


def summarize_final_analysis(messages):
    """收尾用的第二次 Bedrock 呼叫（不提供工具）。

    明確要求模型依「市場判斷／關鍵依據／信心說明」三段式結構重新整理輸出。
    回傳：結構化的分析文字（Markdown 格式字串）。
    """
    summarize_prompt = """根據以上所有蒐集到的資料與分析，請用以下三段式結構重新整理你的最終分析：

## 市場判斷
（你的核心結論，需區分事實、推論、結論三個層次）

## 關鍵依據
（每條依據需標明對應的 evidence_id，說明該證據如何支撐你的判斷）

## 信心說明
（你對結論的信心程度、已知限制、資料不足之處、互相矛盾的訊號如何取捨、什麼情況會推翻結論）

請用繁體中文輸出，保持專業但易懂。不要給出任何投資建議（不說買進、賣出、目標價、建議持有）。"""

    # 在對話歷史尾部加上摘要要求
    summarize_messages = messages.copy()
    summarize_messages.append({
        "role": "user",
        "content": [{"text": summarize_prompt}]
    })

    try:
        # 第二次呼叫不提供工具
        response = call_bedrock(summarize_messages, tool_config=None)

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
