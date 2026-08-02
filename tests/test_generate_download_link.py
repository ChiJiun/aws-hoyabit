"""storage.generate_download_link 的本機與 S3 契約測試。"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))


class TestGenerateDownloadLinkLocal:
    @patch("storage.DATA_BUCKET", "")
    def test_returns_absolute_local_path_when_bucket_empty(self):
        from storage import generate_download_link

        result = generate_download_link("abc123", "report.md")
        assert Path(result).is_absolute()
        assert result.replace("\\", "/").endswith("outputs/abc123/report.md")

    @patch("storage.DATA_BUCKET", None)
    def test_local_path_contains_run_and_filename(self):
        from storage import generate_download_link

        result = generate_download_link("test", "evidence_list.json")
        assert "outputs/test/evidence_list.json" in result.replace("\\", "/")

    @patch("storage.DATA_BUCKET", "")
    def test_returns_string_type(self):
        from storage import generate_download_link

        assert isinstance(generate_download_link("r1", "output.md"), str)


class TestGenerateDownloadLinkS3:
    @patch("storage.DATA_BUCKET", "my-data-bucket")
    @patch("boto3.client")
    def test_calls_generate_presigned_url(self, mock_boto_client):
        mock_s3 = MagicMock()
        expected = "https://my-data-bucket.s3.amazonaws.com/runs/abc/report.md"
        mock_s3.generate_presigned_url.return_value = expected
        mock_boto_client.return_value = mock_s3

        from storage import generate_download_link

        result = generate_download_link("abc", "report.md")
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-data-bucket", "Key": "runs/abc/report.md"},
            ExpiresIn=3600,
        )
        assert result == expected

    @patch("storage.DATA_BUCKET", "my-data-bucket")
    @patch("boto3.client")
    def test_passes_custom_expires_in(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://example.com/presigned"
        mock_boto_client.return_value = mock_s3

        from storage import generate_download_link

        generate_download_link("abc", "file.json", expires_in=7200)
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

        result = generate_download_link("abc", "report.md")
        assert isinstance(result, str)
        assert result.startswith("https://")
