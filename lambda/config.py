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
TOOL_HTTP_TIMEOUT_SECONDS = int(os.environ.get("TOOL_HTTP_TIMEOUT_SECONDS", 15))
TOOL_HTTP_MAX_ATTEMPTS = int(os.environ.get("TOOL_HTTP_MAX_ATTEMPTS", 2))
TOOL_HTTP_BACKOFF_SECONDS = float(os.environ.get("TOOL_HTTP_BACKOFF_SECONDS", 0.25))
TOOL_RETRY_AFTER_MAX_SECONDS = float(os.environ.get("TOOL_RETRY_AFTER_MAX_SECONDS", 2.0))

# ---- 外部 API 金鑰 ----
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY")
CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY")
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

# 各資料類型可接受的最大資料年齡（秒）；由 tools.quality 統一判定。
FRESHNESS_THRESHOLDS_SECONDS = {
    "price_daily": 3 * 24 * 60 * 60,
    "quant_daily": 3 * 24 * 60 * 60,
    "derivatives_snapshot": 5 * 60,
    "orderbook_snapshot": 60,
    "market_dominance": 24 * 60 * 60,
    "news": 14 * 24 * 60 * 60,
    "official_announcement": 30 * 24 * 60 * 60,
    "sentiment": 24 * 60 * 60,
    "macro": 3 * 24 * 60 * 60,
}

# 單源異常門檻集中管理，避免散落於各工具。
ANOMALY_THRESHOLDS = {
    # A1-A5: quant/price（已有）
    "volume_percentile_high": 95.0,
    "volume_percentile_low": 5.0,
    "bollinger_percentile_high": 90.0,
    "bollinger_percentile_low": 10.0,
    "atr_percentile_high": 90.0,
    "adx_percentile_high": 85.0,
    "adx_percentile_low": 15.0,
    "return_zscore_abs": 2.0,
    # A6: sentiment
    "fg_extreme_low": 20,
    "fg_extreme_high": 80,
    "fg_rapid_change_7d": 30,
    # A7: news density
    "news_density_ratio": 3.0,
    "news_density_recent_hours": 48,
    # A8: official event keywords（門檻為命中即標，此處僅記錄時間窗口）
    # A9: onchain
    "onchain_activity_deviation_pct": 30.0,
    # A10: macro
    "macro_change_percentile_high": 85.0,
}


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

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)

    global AWS_REGION, BEDROCK_MODEL_ID, DATA_BUCKET
    global MAX_AGENT_TURNS, TIME_BUDGET_SECONDS
    global TOOL_HTTP_TIMEOUT_SECONDS, TOOL_HTTP_MAX_ATTEMPTS
    global TOOL_HTTP_BACKOFF_SECONDS, TOOL_RETRY_AFTER_MAX_SECONDS
    global COINGECKO_API_KEY, CRYPTOPANIC_API_KEY, ETHERSCAN_API_KEY
    global HELIUS_API_KEY, FRED_API_KEY
    global CMC_API_KEY, COINGLASS_API_KEY
    global REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
    global SOSOVALUE_API_KEY, DUNE_API_KEY

    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID")
    DATA_BUCKET = os.environ.get("DATA_BUCKET")

    MAX_AGENT_TURNS = int(os.environ.get("MAX_AGENT_TURNS", 15))
    TIME_BUDGET_SECONDS = int(os.environ.get("TIME_BUDGET_SECONDS", 600))
    TOOL_HTTP_TIMEOUT_SECONDS = int(os.environ.get("TOOL_HTTP_TIMEOUT_SECONDS", 15))
    TOOL_HTTP_MAX_ATTEMPTS = int(os.environ.get("TOOL_HTTP_MAX_ATTEMPTS", 2))
    TOOL_HTTP_BACKOFF_SECONDS = float(os.environ.get("TOOL_HTTP_BACKOFF_SECONDS", 0.25))
    TOOL_RETRY_AFTER_MAX_SECONDS = float(os.environ.get("TOOL_RETRY_AFTER_MAX_SECONDS", 2.0))

    COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY")
    CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY")
    ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY")
    HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY")
    FRED_API_KEY = os.environ.get("FRED_API_KEY")

    CMC_API_KEY = os.environ.get("CMC_API_KEY")
    COINGLASS_API_KEY = os.environ.get("COINGLASS_API_KEY")
    REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
    SOSOVALUE_API_KEY = os.environ.get("SOSOVALUE_API_KEY")
    DUNE_API_KEY = os.environ.get("DUNE_API_KEY")
