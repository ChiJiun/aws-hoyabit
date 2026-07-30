"""
config.py — 環境變數與常數集中管理

所有環境變數的讀取都集中在這個檔案，其他檔案 import 這裡的變數，
不要在各處散落 os.environ 呼叫。這樣要改設定時只需要動一個地方。
"""

import os

# ---- AWS 設定 ----
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID")
DATA_BUCKET = os.environ.get("DATA_BUCKET")

# ---- 執行參數 ----
MAX_AGENT_TURNS = int(os.environ.get("MAX_AGENT_TURNS", 8))
TIME_BUDGET_SECONDS = int(os.environ.get("TIME_BUDGET_SECONDS", 600))

# ---- 外部 API 金鑰 ----
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY")
CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY")
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY")
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY")
FRED_API_KEY = os.environ.get("FRED_API_KEY")

# ---- 業務常數 ----
SUPPORTED_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
BASELINE_END_DATE = "2026-05-31"   # 賽方基準資料截止日，用來判斷是否需要補即時資料


def load_local_env():
    # 功能：本機開發時，從 .env 檔案載入環境變數。
    # 部署到 Lambda 後不會用到這個函式（Lambda 直接從設定畫面注入環境變數）。
    # 實作：用 python-dotenv 的 load_dotenv() 讀取專案根目錄的 .env。
    pass