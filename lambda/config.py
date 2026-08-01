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
MAX_AGENT_TURNS = int(os.environ.get("MAX_AGENT_TURNS", 15))
TIME_BUDGET_SECONDS = int(os.environ.get("TIME_BUDGET_SECONDS", 600))

# ---- 外部 API 金鑰 ----
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY")
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY")
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY")
FRED_API_KEY = os.environ.get("FRED_API_KEY")

# ---- 預留的外部 API 金鑰（選用，缺少時對應工具 graceful fail）----
CMC_API_KEY = os.environ.get("CMC_API_KEY")
COINGLASS_API_KEY = os.environ.get("COINGLASS_API_KEY")
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
SOSOVALUE_API_KEY = os.environ.get("SOSOVALUE_API_KEY")
DUNE_API_KEY = os.environ.get("DUNE_API_KEY")

# ---- 業務常數 ----
SUPPORTED_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
BASELINE_END_DATE = "2026-05-31"   # 賽方基準資料截止日，用來判斷是否需要補即時資料


def check_required_env():
    """檢查必要環境變數是否已設定，回傳缺少的變數名清單。

    啟動時呼叫一次，一次性列出所有缺漏的變數名，方便部署時快速排錯。
    只檢查「系統運作必須」的變數，API 金鑰視為選用（缺了某支工具會 graceful fail）。
    """
    required = {
        "BEDROCK_MODEL_ID": BEDROCK_MODEL_ID,
        "DATA_BUCKET": DATA_BUCKET,
    }
    missing = [name for name, value in required.items() if not value]
    return missing


def load_local_env():
    """本機開發時，從專案根目錄的 .env 檔案載入環境變數。

    部署到 Lambda 後不會用到這個函式（Lambda 直接從設定畫面注入環境變數）。
    呼叫多次是安全的（冪等），每次都會重新讀取 .env 並刷新模組級變數。
    """
    from pathlib import Path
    from dotenv import load_dotenv

    # .env 位於專案根目錄（lambda/ 的上一層）
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)

    # 重新從 os.environ 刷新所有模組級變數
    global AWS_REGION, BEDROCK_MODEL_ID, DATA_BUCKET
    global MAX_AGENT_TURNS, TIME_BUDGET_SECONDS
    global COINGECKO_API_KEY, ETHERSCAN_API_KEY
    global HELIUS_API_KEY, FRED_API_KEY
    global CMC_API_KEY, COINGLASS_API_KEY
    global REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
    global SOSOVALUE_API_KEY, DUNE_API_KEY

    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID")
    DATA_BUCKET = os.environ.get("DATA_BUCKET")

    MAX_AGENT_TURNS = int(os.environ.get("MAX_AGENT_TURNS", 15))
    TIME_BUDGET_SECONDS = int(os.environ.get("TIME_BUDGET_SECONDS", 600))

    COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY")
    ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY")
    HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY")
    FRED_API_KEY = os.environ.get("FRED_API_KEY")

    CMC_API_KEY = os.environ.get("CMC_API_KEY")
    COINGLASS_API_KEY = os.environ.get("COINGLASS_API_KEY")
    REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
    SOSOVALUE_API_KEY = os.environ.get("SOSOVALUE_API_KEY")
    DUNE_API_KEY = os.environ.get("DUNE_API_KEY")