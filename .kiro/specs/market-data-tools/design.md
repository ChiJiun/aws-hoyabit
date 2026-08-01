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
