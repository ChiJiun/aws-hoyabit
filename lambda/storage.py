"""
storage.py — S3 讀寫與下載連結

所有跟 S3 互動的操作集中在這裡。本機測試時可以讓這些函式改讀寫本地檔案，
這樣同一份程式碼在本機與 Lambda 上都能跑。
"""

import io
from pathlib import Path

import pandas as pd

from config import DATA_BUCKET


# 專案根目錄（lambda/ 的上一層）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def read_baseline_csv(symbol: str) -> pd.DataFrame:
    """從 S3 或本地讀取指定幣種的賽方基準 OHLCV CSV。

    路徑：s3://{DATA_BUCKET}/baseline/{symbol}USDT_daily_ohlcv.csv
    本機：data/baseline/{symbol}USDT_daily_ohlcv.csv

    回傳：pandas DataFrame（欄位：date, open, high, low, close, volume）
    """
    filename = f"{symbol}USDT_daily_ohlcv.csv"

    if DATA_BUCKET:
        # Lambda 環境：從 S3 讀取
        import boto3

        s3_client = boto3.client("s3")
        key = f"baseline/{filename}"
        response = s3_client.get_object(Bucket=DATA_BUCKET, Key=key)
        body = response["Body"].read()
        df = pd.read_csv(io.BytesIO(body))
    else:
        # 本機測試：從本地 data/baseline/ 讀取
        local_path = _PROJECT_ROOT / "data" / "baseline" / filename
        df = pd.read_csv(local_path)

    return df


def save_raw_payload(run_id: str, evidence_id: str, raw_data: dict) -> str:
    """將單次外部 API 呼叫的原始回應封存至 S3（或本機 outputs/ 資料夾）。

    路徑：runs/{run_id}/raw/{evidence_id}.json

    回傳：S3 URI 字串（Lambda 環境）或本機檔案路徑字串（本機測試）。
    """
    import json

    key = f"runs/{run_id}/raw/{evidence_id}.json"
    content = json.dumps(raw_data, ensure_ascii=False, default=str)

    if DATA_BUCKET:
        # Lambda 環境：上傳至 S3
        import boto3

        s3_client = boto3.client("s3")
        s3_client.put_object(
            Bucket=DATA_BUCKET,
            Key=key,
            Body=content,
            ContentType="application/json",
        )
        return f"s3://{DATA_BUCKET}/{key}"
    else:
        # 本機測試：寫入 outputs/ 資料夾
        local_path = _PROJECT_ROOT / "outputs" / run_id / "raw" / f"{evidence_id}.json"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        return str(local_path)


def save_output_file(run_id: str, filename: str, content: str) -> str:
    """將最終交付物（報告、證據清單、執行紀錄）上傳到 S3（或本機 outputs/ 資料夾）。

    路徑：runs/{run_id}/{filename}

    回傳：S3 key 字串（Lambda 環境）或本機檔案路徑字串（本機測試）。
    """
    key = f"runs/{run_id}/{filename}"

    # 根據副檔名決定 ContentType
    if filename.endswith(".json"):
        content_type = "application/json"
    elif filename.endswith(".jsonl"):
        content_type = "application/jsonl"
    elif filename.endswith(".md"):
        content_type = "text/markdown"
    else:
        content_type = "text/plain"

    if DATA_BUCKET:
        # Lambda 環境：上傳至 S3
        import boto3

        s3_client = boto3.client("s3")
        s3_client.put_object(
            Bucket=DATA_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return key
    else:
        # 本機測試：寫入 outputs/ 資料夾
        local_path = _PROJECT_ROOT / "outputs" / run_id / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        return str(local_path)


def generate_download_link(key: str, expires_in: int = 3600) -> str:
    """為 S3 上的檔案產生有時效性的下載連結（presigned URL）。

    這樣資料 bucket 不必設為公開，評審也能點連結下載交付物。

    路徑：s3://{DATA_BUCKET}/{key}
    本機：file:// URI 指向 outputs/ 資料夾內的對應檔案

    回傳：可直接放在網頁上的 https 網址字串（Lambda）或 file:// URI（本機）。
    """
    if DATA_BUCKET:
        # Lambda 環境：產生 S3 presigned URL
        import boto3

        s3_client = boto3.client("s3")
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": DATA_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
        return url
    else:
        # 本機測試：回傳 file:// URI
        local_path = _PROJECT_ROOT / "outputs" / key
        return local_path.as_uri()