"""Tests for storage.save_raw_payload (local mode)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add lambda/ to path so we can import storage
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))


@pytest.fixture(autouse=True)
def clear_data_bucket():
    """Ensure DATA_BUCKET is empty for local-mode tests."""
    with patch("storage.DATA_BUCKET", ""):
        yield


@pytest.fixture
def tmp_project_root(tmp_path):
    """Patch _PROJECT_ROOT to a temp directory for isolation."""
    with patch("storage._PROJECT_ROOT", tmp_path):
        yield tmp_path


class TestSaveRawPayloadLocal:
    """Tests for save_raw_payload in local (non-S3) mode."""

    def test_creates_file_at_expected_path(self, tmp_project_root):
        from storage import save_raw_payload

        run_id = "run-001"
        evidence_id = "ev-abc"
        raw_data = {"price": 50000, "symbol": "BTC"}

        result = save_raw_payload(run_id, evidence_id, raw_data)

        expected_path = tmp_project_root / "outputs" / run_id / "raw" / f"{evidence_id}.json"
        assert expected_path.exists()
        assert result == str(expected_path)

    def test_file_content_is_valid_json(self, tmp_project_root):
        from storage import save_raw_payload

        raw_data = {"key": "value", "nested": {"a": 1}}
        save_raw_payload("run-002", "ev-xyz", raw_data)

        file_path = tmp_project_root / "outputs" / "run-002" / "raw" / "ev-xyz.json"
        content = json.loads(file_path.read_text(encoding="utf-8"))
        assert content == raw_data

    def test_handles_non_serializable_types(self, tmp_project_root):
        """default=str should handle non-serializable types like datetime."""
        from datetime import datetime

        from storage import save_raw_payload

        raw_data = {"timestamp": datetime(2025, 1, 15, 10, 30, 0), "amount": 123.45}
        result = save_raw_payload("run-003", "ev-dt", raw_data)

        file_path = Path(result)
        assert file_path.exists()
        content = json.loads(file_path.read_text(encoding="utf-8"))
        assert content["timestamp"] == "2025-01-15 10:30:00"
        assert content["amount"] == 123.45

    def test_handles_unicode_content(self, tmp_project_root):
        """ensure_ascii=False should preserve unicode characters."""
        from storage import save_raw_payload

        raw_data = {"title": "比特幣分析", "symbol": "BTC"}
        result = save_raw_payload("run-004", "ev-uni", raw_data)

        file_path = Path(result)
        content = file_path.read_text(encoding="utf-8")
        assert "比特幣分析" in content

    def test_returns_local_path_string(self, tmp_project_root):
        from storage import save_raw_payload

        result = save_raw_payload("run-005", "ev-ret", {"data": True})

        assert "run-005" in result
        assert "ev-ret.json" in result
        assert "s3://" not in result


class TestSaveRawPayloadS3:
    """Tests for save_raw_payload in S3 mode (mocked)."""

    def test_uploads_to_s3_and_returns_uri(self):
        from unittest.mock import MagicMock

        mock_s3 = MagicMock()
        bucket_name = "my-data-bucket"

        with patch("storage.DATA_BUCKET", bucket_name), \
             patch("boto3.client", return_value=mock_s3):
            from storage import save_raw_payload

            raw_data = {"price": 42000}
            result = save_raw_payload("run-s3", "ev-s3", raw_data)

        assert result == f"s3://{bucket_name}/runs/run-s3/raw/ev-s3.json"
        mock_s3.put_object.assert_called_once_with(
            Bucket=bucket_name,
            Key="runs/run-s3/raw/ev-s3.json",
            Body=json.dumps(raw_data, ensure_ascii=False, default=str),
            ContentType="application/json",
        )
