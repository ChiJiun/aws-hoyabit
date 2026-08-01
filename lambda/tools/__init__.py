"""
tools/ — 資料蒐集工具包

包含以下工具模組（各自獨立，不互相 import）：
- price.py: OHLCV 價格、盤口深度、市值佔比
- quant.py: 技術指標計算（純本地，無外部 API）
- news.py: Google News RSS + 媒體 RSS + 官方公告
- onchain.py: 鏈上資料（依幣種分派五種來源）
- sentiment.py: 市場情緒（alternative.me Fear & Greed）
- macro.py: 總經指標（FRED + 排程事件）
- derivatives.py: 衍生品（Hyperliquid / Binance Futures / Deribit）
- prediction.py: 預測市場（Polymarket）
- defi.py: DeFi TVL、穩定幣供給、GitHub 開發活躍度
- institutional.py: CFTC COT、SEC EDGAR、Coin Metrics Community
"""
