"""
quant.py — 技術指標計算工具

這個工具不呼叫任何外部 API，純粹是本地計算。
存在的理由：所有數字必須由程式決定性地算出來，不能讓模型心算。
模型心算數字是現場 Demo 時最容易被評審驗證出錯的地方。
"""


def compute_quant(symbol, features, window, related_claim, compare_symbol=None):
    # 功能：計算指定的技術指標。
    # 步驟：
    #   1. 取得該幣種的價格資料（呼叫 price.get_price_ohlcv 或讀取快取）
    #   2. 依 features 清單逐一計算對應指標
    #   3. 每個指標同時計算「當前值」與「在歷史資料中的百分位」
    #      —— 百分位比絕對值更有解讀價值，例如「ATR 位於過去一年第 22 百分位」
    #         比「ATR 為 2.1%」更能支撐「波動率處於低位」這個推論
    # features 可能包含：atr_pct、bollinger_bandwidth、adx、range_ratio、
    #                   volume_zscore、realized_vol、correlation
    # content_reference 應包含：指標名稱、計算視窗、計算結果數值、百分位。
    # 回傳：統一格式 dict
    pass


def calc_atr_pct(df, window):
    # 功能：計算 ATR（平均真實區間）並轉成佔價格的百分比。
    # 用途：衡量波動率，是判斷「盤整」的核心指標之一。
    pass


def calc_adx(df, window):
    # 功能：計算 ADX（平均趨向指標）。
    # 用途：衡量趨勢強度。一般以低於 20 視為無明確趨勢，可支持盤整判斷。
    pass


def calc_bollinger_bandwidth(df, window):
    # 功能：計算布林帶寬（上下軌距離佔中軌的比例）。
    # 用途：帶寬收窄代表波動率壓縮，常見於盤整或突破前的醞釀期。
    pass


def calc_percentile_rank(series, current_value, lookback=365):
    # 功能：計算當前數值在過去 lookback 天資料中的百分位。
    # 這是把「絕對數值」轉成「相對歷史位置」的關鍵，讓推論有比較基準。
    pass


def calc_correlation(df_a, df_b, window):
    # 功能：計算兩個幣種報酬率的相關係數。
    # 用途：比較分析題型（範例三）會需要，用來說明兩者風險敞口的差異。
    pass