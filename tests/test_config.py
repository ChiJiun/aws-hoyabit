"""
test_config.py — config.load_local_env 單元測試

確認 load_local_env 能正確從 .env 讀取環境變數並刷新模組級變數。
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))


def test_load_local_env_reads_dotenv(tmp_path, monkeypatch):
    """load_local_env 應從 .env 讀取值並刷新模組級變數。"""
    # 準備：在 tmp 目錄模擬專案結構 (root/.env, root/lambda/config.py)
    env_content = (
        "AWS_REGION=ap-northeast-1\n"
        "BEDROCK_MODEL_ID=test-model-id\n"
        "DATA_BUCKET=test-bucket\n"
        "MAX_AGENT_TURNS=12\n"
        "TIME_BUDGET_SECONDS=300\n"
        "COINGECKO_API_KEY=cg-key-123\n"
        "CRYPTOPANIC_API_KEY=cp-key-456\n"
        "ETHERSCAN_API_KEY=es-key-789\n"
        "HELIUS_API_KEY=hl-key-abc\n"
        "FRED_API_KEY=fred-key-def\n"
    )
    # 寫入 .env 到專案根目錄
    env_file = tmp_path / ".env"
    env_file.write_text(env_content, encoding="utf-8")

    # 建立 lambda 子目錄並放一個假的 config.py 路徑指向
    lambda_dir = tmp_path / "lambda"
    lambda_dir.mkdir()

    # Monkeypatch config 模組的 __file__ 讓 Path(__file__) 解析到 tmp 路徑
    import config
    monkeypatch.setattr(config, "__file__", str(lambda_dir / "config.py"))

    # 先清除可能已有的環境變數
    for key in [
        "AWS_REGION", "BEDROCK_MODEL_ID", "DATA_BUCKET",
        "MAX_AGENT_TURNS", "TIME_BUDGET_SECONDS",
        "COINGECKO_API_KEY", "CRYPTOPANIC_API_KEY",
        "ETHERSCAN_API_KEY", "HELIUS_API_KEY", "FRED_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    # 執行
    config.load_local_env()

    # 驗證：模組級變數已刷新
    assert config.AWS_REGION == "ap-northeast-1"
    assert config.BEDROCK_MODEL_ID == "test-model-id"
    assert config.DATA_BUCKET == "test-bucket"
    assert config.MAX_AGENT_TURNS == 12
    assert config.TIME_BUDGET_SECONDS == 300
    assert config.COINGECKO_API_KEY == "cg-key-123"
    assert config.CRYPTOPANIC_API_KEY == "cp-key-456"
    assert config.ETHERSCAN_API_KEY == "es-key-789"
    assert config.HELIUS_API_KEY == "hl-key-abc"
    assert config.FRED_API_KEY == "fred-key-def"


def test_load_local_env_idempotent(tmp_path, monkeypatch):
    """load_local_env 呼叫多次不應出錯，且能反映最新的 .env 內容。"""
    env_file = tmp_path / ".env"
    env_file.write_text("DATA_BUCKET=bucket-v1\n", encoding="utf-8")

    lambda_dir = tmp_path / "lambda"
    lambda_dir.mkdir()

    import config
    monkeypatch.setattr(config, "__file__", str(lambda_dir / "config.py"))
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    config.load_local_env()
    assert config.DATA_BUCKET == "bucket-v1"

    # 更新 .env 並再次呼叫
    env_file.write_text("DATA_BUCKET=bucket-v2\n", encoding="utf-8")
    config.load_local_env()
    assert config.DATA_BUCKET == "bucket-v2"


def test_load_local_env_defaults_when_missing(tmp_path, monkeypatch):
    """若 .env 缺少某些變數，模組級變數應使用預設值或 None。"""
    # 空 .env
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    lambda_dir = tmp_path / "lambda"
    lambda_dir.mkdir()

    import config
    monkeypatch.setattr(config, "__file__", str(lambda_dir / "config.py"))

    # 清除所有相關環境變數
    for key in [
        "AWS_REGION", "BEDROCK_MODEL_ID", "DATA_BUCKET",
        "MAX_AGENT_TURNS", "TIME_BUDGET_SECONDS",
        "COINGECKO_API_KEY", "CRYPTOPANIC_API_KEY",
        "ETHERSCAN_API_KEY", "HELIUS_API_KEY", "FRED_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    config.load_local_env()

    # 有預設值的變數
    assert config.AWS_REGION == "us-east-1"
    assert config.MAX_AGENT_TURNS == 8
    assert config.TIME_BUDGET_SECONDS == 600

    # 無預設值的變數應為 None
    assert config.BEDROCK_MODEL_ID is None
    assert config.DATA_BUCKET is None
    assert config.COINGECKO_API_KEY is None
