"""
Tests for storage.generate_download_link

驗證 presigned URL 產生邏輯：
- 本機模式：回傳 file:// URI
- Lambda 模式：呼叫 S3 generate_presigned_url 並回傳結果
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))


class TestGenerateDownloadLinkLocal:
    """DATA_BUCKET 未設定時（本機模式）的行為。"""

    @patch("storage.DATA_BUCKET", "")
    def test_returns_file_uri_when_bucket_empty(self):
        from storage import generate_download_link

        result = generate_download_link("runs/abc123/report.md")
        assert result.startswith("file:///")

    @patch("storage.DATA_BUCKET", "")
    def test_file_uri_contains_key_path(self):
        from storage import generate_download_link

        result = generate_download_link("runs/abc123/evidence_list.json")
        assert "runs/abc123/evidence_list.json" in result.replace("\\", "/")

    @patch("storage.DATA_BUCKET", None)
    def test_returns_file_uri_when_bucket_none(self):
        from storage import generate_download_link

        result = generate_download_link("runs/test/file.jsonl")
        assert result.startswith("file:///")

    @patch("storage.DATA_BUCKET", "")
    def test_returns_string_type(self):
        from storage import generate_download_link

        result = generate_download_link("runs/r1/output.md")
        assert isinstance(result, str)


class TestGenerateDownloadLinkS3:
    """DATA_BUCKET 有設定時（Lambda 模式）的行為。"""

    @patch("storage.DATA_BUCKET", "my-data-bucket")
    @patch("boto3.client")
    def test_calls_generate_presigned_url(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://my-data-bucket.s3.amazonaws.com/runs/abc/report.md?X-Amz-Signature=..."
        mock_boto_client.return_value = mock_s3

        from storage import generate_download_link

        result = generate_download_link("runs/abc/report.md")

        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-data-bucket", "Key": "runs/abc/report.md"},
            ExpiresIn=3600,
        )
        assert result == "https://my-data-bucket.s3.amazonaws.com/runs/abc/report.md?X-Amz-Signature=..."

    @patch("storage.DATA_BUCKET", "my-data-bucket")
    @patch("boto3.client")
    def test_passes_custom_expires_in(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://example.com/presigned"
        mock_boto_client.return_value = mock_s3

        from storage import generate_download_link

        generate_download_link("runs/abc/file.json", expires_in=7200)

        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-data-bucket", "Key": "runs/abc/file.json"},
            ExpiresIn=7200,
        )

    @patch("storage.DATA_BUCKET", "my-data-bucket")
    @patch("boto3.client")
    def test_returns_url_string(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://presigned-url.example.com"
        mock_boto_client.return_value = mock_s3

        from storage import generate_download_link

        result = generate_download_link("runs/abc/report.md")
        assert isinstance(result, str)
        assert result.startswith("https://")
