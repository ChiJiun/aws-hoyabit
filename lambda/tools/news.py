"""
news.py — 新聞與官方公告工具

資料來源：CryptoPanic、各專案官方部落格 RSS、GitHub releases
"""


def search_news(symbol, lookback_days, related_claim, keywords=None):
    # 功能：查詢指定幣種在近期的新聞、官方公告與監管消息。
    # 步驟：
    #   1. 呼叫 CryptoPanic API（帶 currencies 參數過濾幣種）
    #   2. 呼叫 fetch_official_announcements() 取得一手官方消息
    #   3. 兩邊結果合併、依發布時間排序
    # content_reference 應包含：標題、發布時間、原文網址、引用片段。
    # 注意：一則通稿常被多家媒體轉載，摘要中應標註哪些來自同一來源家族，
    #      避免模型誤判為「多源共識」。
    # 回傳：統一格式 dict
    pass


def fetch_official_announcements(symbol):
    # 功能：抓取專案官方的一手消息（公告、版本發布、重大更新排程）。
    # 來源：官方部落格 RSS、GitHub releases API。
    # 為什麼優先抓：官方公告是可信度最高的一手來源，且「已排定的事件」
    #              （代幣解鎖、協議升級）往往是判斷市場方向最有力的依據，
    #              純看價格與情緒的分析會完全漏掉這一塊。
    # 回傳：公告清單
    pass