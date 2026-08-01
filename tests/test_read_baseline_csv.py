"""
test_read_baseline_csv.py — read_baseline_csv 函式的單元測試

Validates: Requirements 18.1
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import io

# 確保 lambda 目錄在搜尋路徑中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda'))

import pandas as pd
import pytest


# 測試用 CSV 資料
SAMPLE_CSV = "date,open,high,low,close,volume\n2024-01-01,42000,43000,41000,42500,1000\n2024-01-02,42500,44000,42000,43500,1200\n"


class TestReadBaselineCsvLocal:
    """本機模式測試（DATA_BUCKET 為空）"""

    def test_reads_local_csv_when_data_bucket_not_set(self, tmp_path):
        """DATA_BUCKET 為 None 時，從本地 data/baseline/ 讀取 CSV"""
        # Arrange: 建立假的 baseline 目錄結構
        baseline_dir = tmp_path / "data" / "baseline"
        baseline_dir.mkdir(parents=True)
        csv_file = baseline_dir / "BTCUSDT_daily_ohlcv.csv"
        csv_file.write_text(SAMPLE_CSV)

        with patch("storage.DATA_BUCKET", None), \
             patch("storage._PROJECT_ROOT", tmp_path):
            from storage import read_baseline_csv

            # Act
            df = read_baseline_csv("BTC")

            # Assert
            assert isinstance(df, pd.DataFrame)
            assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
            assert len(df) == 2
            assert df.iloc[0]["close"] == 42500

    def test_constructs_correct_filename_from_symbol(self, tmp_path):
        """確認檔名格式為 {symbol}USDT_daily_ohlcv.csv"""
        baseline_dir = tmp_path / "data" / "baseline"
        baseline_dir.mkdir(parents=True)
        csv_file = baseline_dir / "ETHUSDT_daily_ohlcv.csv"
        csv_file.write_text(SAMPLE_CSV)

        with patch("storage.DATA_BUCKET", None), \
             patch("storage._PROJECT_ROOT", tmp_path):
            from storage import read_baseline_csv

            df = read_baseline_csv("ETH")
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2

    def test_raises_file_not_found_for_missing_csv(self, tmp_path):
        """本機模式下若 CSV 不存在，應拋出 FileNotFoundError"""
        baseline_dir = tmp_path / "data" / "baseline"
        baseline_dir.mkdir(parents=True)

        with patch("storage.DATA_BUCKET", None), \
             patch("storage._PROJECT_ROOT", tmp_path):
            from storage import read_baseline_csv

            with pytest.raises(FileNotFoundError):
                read_baseline_csv("DOGE")


class TestReadBaselineCsvS3:
    """S3 模式測試（DATA_BUCKET 有值）"""

    def test_reads_from_s3_when_data_bucket_is_set(self):
        """DATA_BUCKET 有值時，透過 boto3 從 S3 讀取"""
        mock_s3_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = SAMPLE_CSV.encode("utf-8")
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        with patch("storage.DATA_BUCKET", "my-test-bucket"), \
             patch("boto3.client", return_value=mock_s3_client):
            from storage import read_baseline_csv

            df = read_baseline_csv("BTC")

            # 驗證 S3 呼叫
            mock_s3_client.get_object.assert_called_once_with(
                Bucket="my-test-bucket",
                Key="baseline/BTCUSDT_daily_ohlcv.csv"
            )
            # 驗證結果
            assert isinstance(df, pd.DataFrame)
            assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
            assert len(df) == 2

    def test_s3_key_format(self):
        """確認 S3 key 格式為 baseline/{symbol}USDT_daily_ohlcv.csv"""
        mock_s3_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = SAMPLE_CSV.encode("utf-8")
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        with patch("storage.DATA_BUCKET", "bucket-name"), \
             patch("boto3.client", return_value=mock_s3_client):
            from storage import read_baseline_csv

            read_baseline_csv("SOL")

            mock_s3_client.get_object.assert_called_once_with(
                Bucket="bucket-name",
                Key="baseline/SOLUSDT_daily_ohlcv.csv"
            )
