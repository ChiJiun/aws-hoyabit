# market-data-tools 設計

## 定位
「數字的唯一來源」。所有報告中的量化數值都由本模組決定性計算,禁止 LLM 心算(R11)。
依賴:僅 config、storage(契約 C3)。不 import 其他 tools、agent、report。

## price.py
- `get_price_ohlcv(symbol, start_date, end_date, related_claim) -> dict(C1)`
- 流程:read_baseline_csv → 若 end_date > BASELINE_END_DATE → fetch_recent_from_exchange(Binance {symbol}USDT 日線)→ check_data_seam(重疊日收盤價差 %)→ 拼接 → 篩選
- CoinGecko 為備援路徑(Binance 失敗時);全部失敗 → error dict
- summary:期間、起訖價、漲跌幅、最大回撤、量能概況(~10 行內)

## quant.py
- `compute_quant(symbol, features: list[str], window, compare_symbol=None, related_claim) -> dict(C1)`
- 純函式庫:calc_atr_pct / calc_bollinger_bandwidth / calc_adx / calc_volume_zscore / calc_realized_vol / calc_correlation / calc_percentile_rank
- 每個指標輸出 {value, percentile_rank(0-100), window},百分位讓 LLM 能說「處於近一年第 X 百分位」而非空談數值
- correlation 僅在 compare_symbol 提供時計算,值域 [-1,1]

## 測試重點
P12 任何輸入不拋例外|P14 指標必附百分位|P15 相關係數值域|接縫校驗警告觸發|資料不足 error dict


## Pipeline Presentation 設計增補

### Series adapter

- `extract_price_series(price_result, max_days=90)`：從標準 C1 raw 取 UTC 日線，排序、去重、過濾 non-finite，回傳 points + metadata。
- `calc_relative_strength_series(df_a, df_b, max_days=90)`：按 UTC date inner join，驗證 unit/quote/comparability，計算 `close_a / close_b`；不 forward-fill。
- `compute_quant(..., features=["correlation", "relative_strength"])`：相關係數仍回 scalar + percentile metadata，相對強弱在 raw 另保留 series，summary 只放首末值與變化。

Series metadata 至少包含 `as_of/timeframe/window/unit/symbols/pairs/provider/comparability_notes`。Report 只搬運已計算序列，不得重新 join 或計算比值。

測試涵蓋日期錯位、時區、重複日期、NaN/Inf、零分母、少於兩點、不同 quote、fallback comparability 及 91 日裁切。property test 保證輸出日期嚴格遞增且所有值 finite。
