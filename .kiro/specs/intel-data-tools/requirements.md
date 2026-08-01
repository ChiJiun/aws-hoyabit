# intel-data-tools 需求

範圍:lambda/tools/news.py、onchain.py、sentiment.py、macro.py。編號引用主 spec。

## 承接的主 spec 需求
- **R7 新聞與官方公告**(全部):Google News RSS + 媒體 RSS + 官方部落格/GitHub releases(取代主 spec R7.1 的 CryptoPanic,改用免費來源,語意不變);同來源家族去重標註;content_reference 含標題/時間/URL/引用片段
- **R8 鏈上資料**(全部):BTC→mempool.space、ETH→Etherscan V2、BNB→Blockscout、SOL→Helius、XRP→XRPL;content_reference 含 endpoint/參數/時間範圍
- **R9 市場情緒**(全部):alternative.me Fear & Greed 當前值 + 走勢
- **R10 總體經濟**(全部):FRED(DXY、10Y 殖利率、聯邦基金利率)+ 重要總經事件
- **R20 工具回傳格式統一**(全部):契約 C1

## 本模組補充驗收條件
1. THE 四個工具 SHALL 各自可獨立測試與獨立失敗,單一工具失敗不影響其他工具(分工邊界)
2. WHEN 新聞結果多篇來自同一媒體集團或同一原始報導,THE news 工具 SHALL 於 summary 標註「同源」,防止偽多源共識
3. THE 每個工具 SHALL 設定單次呼叫 timeout ≤ 10 秒,含重試總耗時 ≤ 25 秒
4. WHEN news 收到 lookback_days,THE news 工具 SHALL 正規化發布時間為 UTC 並排除回溯範圍外或無發布時間資料(R7.6)
5. THE intel 工具 SHALL 在 content_reference 保留 API endpoint 供重現,並在可行時另提供人類可讀原文、官方圖表或區塊瀏覽器連結(R12.7)

## Pipeline Presentation 補充需求

本模組的 pipeline 範圍延伸至已註冊的非價格能力（derivatives、prediction、DeFi）；既有 news/onchain/sentiment/macro 邊界不變。

1. WHEN derivatives provider 支援歷史資料，THE tool SHALL 在 raw 保留最多近 90 日的 funding/OI 序列，並標示 exchange、contract、interval、unit 與 as_of；只有 snapshot 時 SHALL 明確標示 `series_unavailable`。
2. WHEN DefiLlama 供給資料可用，THE tool SHALL 保留穩定幣供給量/TVL 的近 90 日升冪序列及 chain/asset/unit；不得把跨鏈總量與單鏈數值直接比較。
3. WHEN news、prediction 或 macro 提供事件日期，THE tool SHALL 正規化為 UTC/date 並提供 Report 可搬運的 watchlist/event series；日期或來源不明項目不得偽裝成確定事件。
4. THE full series SHALL 留在 raw/Evidence，C1 summary SHALL 只含最新值、變化、範圍與異常；所有點必須 finite、去重並可追溯 provider/endpoint。
5. WHEN 歷史 series 取得失敗但 snapshot 成功，THE tool SHALL 保留 snapshot 成功結果並將 series 缺口寫入 quality/comparability metadata，不得把整支工具降為完全失敗。
6. THE Report SHALL 可依 capability ID 取得序列，不依 provider 特定 raw schema；因此每支工具 SHALL 提供穩定的 `raw.series` 或 documented adapter key。
