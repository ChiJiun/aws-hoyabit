"""
agent.py — Agent 主迴圈與工具規格

這是整個系統的核心。run_agent_loop 維持「呼叫模型 → 判斷模型是否要用工具
→ 分派到對應工具 → 把結果餵回模型」的循環，直到模型認為證據足夠。
"""

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
    # 功能：組出一份 JSON，告訴 Bedrock 有哪些工具可用、每個工具的參數長什麼樣。
    # 格式：{"tools": [{"toolSpec": {"name": ..., "description": ..., "inputSchema": {...}}}, ...]}
    # 重點：每個工具的 inputSchema 都要把 related_claim 列入 required，
    #      這是強制 LLM 說明取數目的的機制。
    # 回傳：dict，可直接傳給 converse() 的 toolConfig 參數
    pass


def call_bedrock(messages, tool_config):
    # 功能：呼叫 Bedrock Converse API 一次。
    # 實作：boto3.client("bedrock-runtime").converse(
    #          modelId=BEDROCK_MODEL_ID,
    #          messages=messages,
    #          system=[{"text": SYSTEM_PROMPT}],
    #          toolConfig=tool_config)
    # 回傳：API 的完整回應 dict（呼叫方需檢查 stopReason 與 output.message）
    pass


def dispatch_tool_call(run_id, tool_use_block):
    # 功能：根據模型指定的工具名稱，找到對應函式並執行，然後記錄證據。
    # 步驟：
    #   1. 從 tool_use_block 取出 name 與 input（參數）
    #   2. 從 TOOL_DISPATCH 找到對應函式
    #   3. 執行該函式，計時
    #   4. 呼叫 evidence.log_evidence() 記錄四欄位證據
    #   5. 呼叫 evidence.log_execution_step() 記錄執行紀錄
    #   6. 把結果包成 Bedrock 要求的 toolResult 格式
    # 注意：只回傳精簡摘要與 evidence_id 給模型，不回傳完整原始資料，
    #      避免 context 膨脹。
    # 回傳：toolResult 區塊 dict
    pass


def run_agent_loop(run_id, question):
    # 功能：系統核心。維持 Agent 的對話迴圈直到模型完成分析。
    # 流程：
    #   1. 把 question 組成第一則 user 訊息，放進 messages
    #   2. 進入迴圈（最多 MAX_AGENT_TURNS 輪）：
    #        a. 呼叫 call_bedrock()
    #        b. 把模型回應加進 messages（維持對話歷史）
    #        c. 檢查 response["stopReason"]：
    #             "tool_use"  → 取出 toolUse 區塊，呼叫 dispatch_tool_call()，
    #                           把 toolResult 加進 messages，繼續迴圈
    #             "end_turn"  → 模型講完了，跳出迴圈
    #        d. 檢查是否超出時間預算，超出就強制跳出
    #   3. 迴圈結束後回傳完整對話歷史
    # 回傳：messages 陣列（最後一則模型訊息即為分析內容）
    pass


def summarize_final_analysis(messages):
    # 功能：收尾用的第二次 Bedrock 呼叫（不提供工具）。
    #      明確要求模型依「市場判斷／關鍵依據／信心說明」三段式結構重新整理輸出。
    # 為什麼需要：模型在漫長的工具呼叫過程中順手寫出的內容格式常常不穩定，
    #            多一次專門收尾的呼叫可確保報告一定含命題要求的三個章節。
    # 回傳：結構化的分析文字（Markdown 格式字串）
    pass