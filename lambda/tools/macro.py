"""
macro.py — 總體經濟工具

資料來源：FRED（美國聖路易聯準銀行經濟資料庫）
"""


def get_macro(indicators, related_claim, lookback_days=90):
    # 功能：取得總體經濟指標的近期走勢。
    # indicators 可能包含：美元指數（DXY）、10 年期公債殖利率、聯邦基金利率。
    # 用途：比較分析題型會提到「當前宏觀環境」，這類資料能支撐該部分的判斷。
    # content_reference 應包含：FRED series ID、查詢時間範圍、數值序列摘要。
    # 回傳：統一格式 dict
    pass


def fetch_upcoming_events():
    # 功能：取得未來已排定的重要總經事件日期（FOMC 會議、CPI 公布日）。
    # 為什麼重要：「已排定的事件」是判斷短期方向性最有力的證據之一。
    #            例如三天後有 FOMC 會議，就足以推翻「短期缺乏明確方向」的假設。
    #            這類資料在日曆上、不在價格數據裡，容易被忽略。
    # 回傳：事件清單（日期、事件名稱）
    pass