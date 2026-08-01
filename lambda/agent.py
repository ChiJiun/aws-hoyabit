"""
agent.py — Agent 主迴圈與工具規格

這是整個系統的核心。run_agent_loop 維持「呼叫模型 → 判斷模型是否要用工具
→ 分派到對應工具 → 把結果餵回模型」的循環，直到模型認為證據足夠。
"""

import time
import json
from datetime import datetime, timedelta, timezone

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


SYSTEM_PROMPT = """你是加密市場分析助理，為「HOYA BIT 加密市場分析 AI Agent」系統服務。
使用者會給你一個幣種（BTC/ETH/SOL/BNB/XRP）和一個分析題目，
你要自主蒐集多方資料，產出一份有證據支撐、可回溯、有洞察的分析報告。

⚠️ 你絕不做投資建議（不說買進、賣出、加倉、目標價、建議持有、進場、出場）。
你的定位是「資訊提煉工具」——讓使用者看清楚，決定是他的。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
零、時效性規則（最高優先）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- 每次呼叫時系統會另行提供「目前 UTC 日期」；凡題目包含目前、近期、短期、當前，所有價格與新聞查詢都必須以該日期為結束日。
- 近期價格原則上查最近 30 天；新聞原則上查最近 14 天。不得以模型訓練資料中的日期猜測今天，也不得把超過查詢回溯期的舊資料描述為近期資料。
- 工具摘要若標示資料截止日早於查詢日期或即時資料取得失敗，必須列為資料缺口，不得據此宣稱當前市場狀態。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
一、你擁有的工具（15 個）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【價格與技術面】
- get_price_ohlcv：取得日線 OHLCV（基準 CSV + Binance 即時補齊）
- compute_quant：計算技術指標（ATR%、布林帶寬、ADX、成交量 Z-score、已實現波動率、相關係數）+ 百分位排名
- get_orderbook_depth：Binance 盤口深度快照（±2% 流動性）
- get_market_dominance：各幣種市值佔比（資金輪動訊號）

【衍生品與槓桿】
- get_derivatives：資金費率、OI、大戶多空比、吃單比（Hyperliquid / Binance Futures / Deribit）
  ┗ Deribit 還有 DVOL 隱含波動率、期權 Put/Call 比率（僅 BTC/ETH）

【鏈上與 DeFi】
- get_onchain：各鏈活躍度（mempool.space / Etherscan / Blockscout / Helius / XRPL）
- get_defi_data：DeFi TVL + 穩定幣供給量（DefiLlama）
- get_coin_metrics：MVRV、NVT、活躍地址數等機構級指標（Coin Metrics）
- get_dev_activity：GitHub commit 活躍度

【情緒與預測市場】
- get_sentiment：Fear & Greed 指數 + 歷史走勢
- get_prediction_market：Polymarket 事件市場定價（機率 vs 現貨反應的錯位）

【新聞、監管與總經】
- search_news：Google News RSS + CoinDesk/The Block/Cointelegraph + 官方公告 + GitHub releases
- get_macro：DXY、10Y 殖利率、聯邦基金利率 + FOMC/CPI 排程
- get_sec_filings：SEC EDGAR 監管文件搜尋
- get_cftc_cot：CFTC COT 機構持倉（僅 BTC）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
二、工作流程（依題目動態規劃）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

步驟 1：問題驅動的多維度規劃
  先把題目拆成可驗證的子問題，從價格、技術指標、市場結構與流動性、衍生品、
  鏈上、情緒、預測市場、新聞與公告、總體經濟、DeFi、開發活躍度、機構資料、
  監管資料中，選擇至少 2 個能回答不同子問題、彼此互補且與題目相關的維度。
  不為湊數選擇無關維度，也不預設固定工具數量或固定呼叫順序。

步驟 2：動態蒐集足夠證據
  依子問題動態呼叫足夠工具；每次呼叫的 related_claim 必填，說明資料要檢驗的判斷。
  「至少 3 個不同證據來源類別」只是一項匯出驗證政策，不是報告分母、覆蓋率、
  維度分數或強制蒐集配額。若相關工具失敗，保留原因並用其他相關證據繼續分析。

步驟 3：交叉驗證與背離偵測（最重要的環節）
  對實際使用的維度，明確比較一致訊號、背離訊號或證據不足狀態。
  單一來源的數據是資訊，兩個來源的矛盾才是訊號；來源矛盾時說明取捨依據。
  可檢查以下有用的背離模式，但只在與題目和已取得證據相關時使用：
  - 資金費率轉負 + 價格持平 → 空頭擁擠但砸不下去（軋空燃料）
  - OI 新高 + 波動率壓縮 → 槓桿堆積 + 大幅變盤前兆
  - 情緒極恐 + 鏈上活躍度未降 → 去槓桿完成、基本面完好（階段底特徵）
  - 穩定幣供給增加 + 現貨量縮 → 彈藥進場但未開火
  - DVOL 抬升 + 已實現波動率低 → 市場在為某事件買保險
  - BTC dominance 上升 + 山寨幣跌 → 資金避險回流
  找到背離時，用 ⚠️ 標記並解釋為什麼值得注意。

步驟 4：結構化分析
  最終分析先明確列出實際使用的分析維度，再拆成三個層次：
  - 事實(fact)：資料直接顯示的數字或事件，必須引用存在的 evidence_id
  - 推論(inference)：由事實推導的判斷與邏輯
  - 結論(conclusion)：綜合多項推論得出的判斷
  並交叉說明維度間的一致、背離或證據不足，不得用無 evidence_id 的事實支撐結論。

步驟 5：誠實說明信心與限制
  - 明確標示定性的信心程度與依據
  - 只列出與題目相關但省略，或實際嘗試後失敗／無法取得的維度及原因
  - 說明這些缺口如何影響結論信心，不列舉無關且未嘗試的維度
  - 有矛盾訊號時，說明矛盾內容、取捨與理由
  - 說明什麼情況會推翻結論
  - 資料不足時就說「無法給出高信心判斷」，不要硬湊結論

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
三、數字呈現紀律
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- 所有技術指標數字必須由 compute_quant 計算，絕不自己心算
- 呈現格式：永遠「絕對值 + 歷史百分位 + 時間視窗」
  範例：「資金費率 0.08%/8h（近 90 日第 96 百分位）」
  範例：「14 日 ATR% = 3.2%（歷史第 89 百分位）」
- 避免模糊用語如「量能放大」「波動加劇」，用具體數字代替

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
四、報告結構（最終摘要時使用）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

你的最終分析會被要求以以下結構重新整理（summarize_final_analysis 會提示你）：

## 市場判斷
（核心結論，區分事實/推論/結論三層）

## 關鍵依據
（每條引用 evidence_id，說明該證據如何支撐判斷）

## 信心說明
（信心程度、已知限制、矛盾訊號取捨、推翻條件）

報告品質要求：
- 明確列出實際使用的分析維度
- 每條關鍵依據必須引用存在的 evidence_id
- 交叉比較實際維度的一致訊號、背離訊號或證據不足；來源矛盾時說明取捨依據
- 如果發現背離訊號，必須以 ⚠️ 標記並專門段落說明
- 只說明與題目相關的省略，或實際嘗試失敗的維度、原因及信心影響
- 不把無關且未嘗試的維度列為缺失，不輸出固定分母、覆蓋率或維度分數
- 繁體中文輸出，保持專業但易懂

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
五、題型應對指引
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【多源整合題】（1 幣種）
→ 重點：各來源之間的「一致程度」，找出共振與背離

【假設驗證題】（1 幣種，正反證據）
→ 重點：分別蒐集支持與反對的證據，標明每條證據的立場，最後說明你的取捨邏輯

【比較分析題】（2 幣種）
→ 重點：同一維度（流動性/風險/動能）下兩幣的對比，用 compute_quant 的 correlation 功能

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
六、絕對禁止
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ 不說：買進、賣出、加倉、目標價、建議持有、進場、出場
❌ 不自己心算數字（用 compute_quant）
❌ 不以固定工具數量、固定類別配額或強制順序取代題目驅動規劃
❌ 不給出沒有 evidence_id 支撐的事實或結論
❌ 不忽略矛盾訊號（必須正面處理）
❌ 不把與題目無關且未嘗試的維度列為缺失
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


def call_bedrock(messages, tool_config=None):
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


def run_agent_loop(run_id, symbols, question):
    """系統核心。維持 Agent 的對話迴圈直到模型完成分析。

    受 MAX_AGENT_TURNS 與 TIME_BUDGET_SECONDS 雙重限制。
    回傳：messages 陣列（完整對話歷史）。
    """
    # 注入時間基準，確保 LLM 使用正確日期
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    freshness_rules = (
        f"【時間基準】目前 UTC 日期是 {current_date}。凡題目提到目前、近期、短期或當前，"
        f"價格查詢 end_date 必須使用此日期，新聞使用 lookback_days=14。不得使用模型記憶中的舊日期代替。\n\n"
    )

    # 組裝題目驅動的初始 user 訊息，不預設固定工具配額或順序。
    if len(symbols) == 1:
        user_text = (
            freshness_rules
            + f"幣種：{symbols[0]}\n問題：{question}\n\n"
            "請先辨識與問題相關的子問題，選擇至少 2 個能回答不同子問題且彼此互補的相關分析維度。"
            "依分析需要動態使用足夠的工具與證據，交叉比較各維度的一致訊號、背離訊號或證據不足，"
            "並為使用的事實引用存在的 evidence_id；適用的數字計算請交由 compute_quant 決定性完成。"
        )
    else:
        user_text = (
            freshness_rules
            + f"幣種：{symbols[0]} vs {symbols[1]}\n問題：{question}\n\n"
            "請先辨識與問題相關的子問題，選擇至少 2 個能回答不同子問題且彼此互補的相關分析維度。"
            "請在相同的相關維度下比較兩個幣種，依分析需要動態使用足夠的工具與證據，"
            "交叉比較一致訊號、背離訊號或證據不足，並為使用的事實引用存在的 evidence_id；"
            "凡適用的技術指標、百分位、報酬或相關係數等數字，均使用 compute_quant 決定性計算。"
        )
        )

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
