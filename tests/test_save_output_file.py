"""Tests for storage.save_output_file (local and S3 modes)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestSaveOutputFileLocal:
    """Tests for save_output_file in local (non-S3) mode."""

    def test_creates_file_at_expected_path(self, tmp_project_root):
        from storage import save_output_file

        run_id = "run-001"
        filename = "report.md"
        content = "# Analysis Report\nBTC is bullish."

        result = save_output_file(run_id, filename, content)

        expected_path = tmp_project_root / "outputs" / run_id / filename
        assert expected_path.exists()
        assert result == str(expected_path)

    def test_file_content_matches_input(self, tmp_project_root):
        from storage import save_output_file

        content = '{"evidence": [{"id": "ev-1"}]}'
        save_output_file("run-002", "evidence.json", content)

        file_path = tmp_project_root / "outputs" / "run-002" / "evidence.json"
        assert file_path.read_text(encoding="utf-8") == content

    def test_handles_unicode_content(self, tmp_project_root):
        from storage import save_output_file

        content = "# 分析報告\n比特幣趨勢看漲"
        result = save_output_file("run-003", "report.md", content)

        file_path = Path(result)
        assert file_path.read_text(encoding="utf-8") == content

    def test_creates_parent_directories(self, tmp_project_root):
        from storage import save_output_file

        save_output_file("run-deep", "report.md", "content")

        expected_path = tmp_project_root / "outputs" / "run-deep" / "report.md"
        assert expected_path.exists()

    def test_returns_local_path_string(self, tmp_project_root):
        from storage import save_output_file

        result = save_output_file("run-004", "log.jsonl", '{"step":1}')

        assert "run-004" in result
        assert "log.jsonl" in result
        assert "s3://" not in result


class TestSaveOutputFileS3:
    """Tests for save_output_file in S3 mode (mocked)."""

    def test_uploads_md_to_s3_with_correct_content_type(self):
        mock_s3 = MagicMock()
        bucket_name = "my-data-bucket"

        with patch("storage.DATA_BUCKET", bucket_name), \
             patch("boto3.client", return_value=mock_s3):
            from storage import save_output_file

            content = "# Report\nBTC analysis"
            result = save_output_file("run-s3", "report.md", content)

        assert result == "runs/run-s3/report.md"
        mock_s3.put_object.assert_called_once_with(
            Bucket=bucket_name,
            Key="runs/run-s3/report.md",
            Body=content.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
        )

    def test_uploads_json_to_s3_with_correct_content_type(self):
        mock_s3 = MagicMock()
        bucket_name = "my-data-bucket"

        with patch("storage.DATA_BUCKET", bucket_name), \
             patch("boto3.client", return_value=mock_s3):
            from storage import save_output_file

            content = '{"key": "value"}'
            result = save_output_file("run-s3", "evidence.json", content)

        assert result == "runs/run-s3/evidence.json"
        mock_s3.put_object.assert_called_once_with(
            Bucket=bucket_name,
            Key="runs/run-s3/evidence.json",
            Body=content.encode("utf-8"),
            ContentType="application/json",
        )

    def test_uploads_jsonl_to_s3_with_correct_content_type(self):
        mock_s3 = MagicMock()
        bucket_name = "my-data-bucket"

        with patch("storage.DATA_BUCKET", bucket_name), \
             patch("boto3.client", return_value=mock_s3):
            from storage import save_output_file

            content = '{"step":1}\n{"step":2}'
            result = save_output_file("run-s3", "log.jsonl", content)

        assert result == "runs/run-s3/log.jsonl"
        mock_s3.put_object.assert_called_once_with(
            Bucket=bucket_name,
            Key="runs/run-s3/log.jsonl",
            Body=content.encode("utf-8"),
            ContentType="application/x-ndjson",
        )

    def test_returns_s3_key(self):
        mock_s3 = MagicMock()
        bucket_name = "test-bucket"

        with patch("storage.DATA_BUCKET", bucket_name), \
             patch("boto3.client", return_value=mock_s3):
            from storage import save_output_file

            result = save_output_file("run-key", "file.txt", "hello")

        assert result == "runs/run-key/file.txt"
