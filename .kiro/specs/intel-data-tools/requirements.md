# intel-data-tools 需求

範圍:lambda/tools/news.py、onchain.py、sentiment.py、macro.py。編號引用主 spec。

## 承接的主 spec 需求
- **R7 新聞與官方公告**(全部):CryptoPanic + 官方部落格/GitHub releases;同來源家族去重標註;content_reference 含標題/時間/URL/引用片段
- **R8 鏈上資料**(全部):BTC→mempool.space、ETH→Etherscan V2、BNB→Blockscout、SOL→Helius、XRP→XRPL;content_reference 含 endpoint/參數/時間範圍
- **R9 市場情緒**(全部):alternative.me Fear & Greed 當前值 + 走勢
- **R10 總體經濟**(全部):FRED(DXY、10Y 殖利率、聯邦基金利率)+ 重要總經事件
- **R20 工具回傳格式統一**(全部):契約 C1

## 本模組補充驗收條件
1. THE 四個工具 SHALL 各自可獨立測試與獨立失敗,單一工具失敗不影響其他工具(分工邊界)
2. WHEN 新聞結果多篇來自同一媒體集團或同一原始報導,THE news 工具 SHALL 於 summary 標註「同源」,防止偽多源共識
3. THE 每個工具 SHALL 設定單次呼叫 timeout ≤ 10 秒,含重試總耗時 ≤ 25 秒
