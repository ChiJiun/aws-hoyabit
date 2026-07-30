"""
price.py — 價格與 OHLCV 資料工具

資料來源：賽方基準 CSV（S3）＋ Binance 公開 API／CoinGecko（補即時）
"""


def get_price_ohlcv(symbol, start_date, end_date, related_claim):
    # 功能：取得指定幣種在指定期間的日線 OHLCV 資料。
    # 步驟：
    #   1. storage.read_baseline_csv(symbol) 讀取賽方基準資料
    #   2. 檢查 end_date 是否超過 BASELINE_END_DATE（2026-05-31）
    #   3. 若超過，呼叫 fetch_recent_from_exchange() 補齊缺口
    #   4. 呼叫 check_data_seam() 驗證兩段資料的接縫
    #   5. 篩選出 start_date ~ end_date 的區間
    # content_reference 應包含：交易對（如 SOLUSDT）、資料區間、資料筆數。
    # 回傳：統一格式 dict（見 tools/__init__.py 說明）
    pass


def fetch_recent_from_exchange(symbol, from_date):
    # 功能：從交易所公開 API 取得基準資料截止日之後的最新日線資料。
    # 為什麼需要：賽方基準 CSV 止於 2026-05-31，但比賽當天必然更晚，
    #            「過去兩週」這類題目的資料完全落在基準資料之外。
    # 重要：要用與基準資料相同的交易對（Binance 的 SOLUSDT 等），
    #      不要混用 CoinGecko 的 USD 報價，否則價格基準不一致。
    # 回傳：pandas DataFrame，欄位與基準 CSV 相同
    pass


def check_data_seam(baseline_df, recent_df):
    # 功能：檢查基準資料與即時資料的接縫是否一致。
    # 實作：找出兩段資料日期重疊的部分，比對收盤價差異百分比。
    # 為什麼做這件事：主動揭露資料拼接點與校驗結果，正面回應命題對
    #                「可回溯的證據管理」的要求，也避免指標計算失真。
    # 回傳：(是否通過, 重疊日數, 最大價差百分比)
    pass