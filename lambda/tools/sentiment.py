"""
sentiment.py — 市場情緒工具

資料來源：alternative.me Fear & Greed Index
免費、不需註冊、不需 API 金鑰，是這次專案取得情緒資料最穩定的途徑。
（Reddit API 自 2025 年 11 月起即使非商業用途也需申請核准、審核 2-4 週，
  時程上不適合這次比賽，故不採用。）
"""


def get_sentiment(related_claim, lookback_days=30):
    # 功能：取得市場恐懼與貪婪指數的當前值與近期走勢。
    # 說明：這是全市場的單一指數（0-100，從極度恐慌到極度貪婪），
    #      五個幣種都參考同一個數值，不需要依幣種分派。
    # content_reference 應包含：API endpoint、查詢的時間範圍、指數數值與分級文字。
    # 注意：這是「情緒代理指標」而非該幣種專屬情緒，
    #      在報告中引用時應說明這個限制。
    # 回傳：統一格式 dict
    pass