"""
storage.py — S3 讀寫與本機 fallback

所有跟 S3 互動的操作集中在這裡。本機測試時（DATA_BUCKET 未設定或無 AWS 憑證），
自動 fallback 至本地檔案系統：
  - 讀取基準 CSV → data/baseline/
  - 寫入原始回應與交付物 → outputs/{run_id}/
  - 產生下載連結 → 回傳本地檔案路徑（無 presigned URL）

這讓同一份程式碼在本機與 Lambda 上都能跑，呼叫端無需改碼。
"""

import io
import json
import os
from pathlib import Path

import pandas as pd

import config

# 專案根目錄（lambda/ 的上一層）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _is_local_mode():
    """判斷是否為本機模式（無 S3 環境）。

    當 DATA_BUCKET 未設定時，所有 S3 操作 fallback 到本地檔案系統。
    """
    return not config.DATA_BUCKET


def _get_s3_client():
    """取得 boto3 S3 client（僅在非本機模式時呼叫）。"""
    import boto3
    return boto3.client("s3", region_name=config.AWS_REGION)


def read_baseline_csv(symbol):
    """從 S3 或本機讀取指定幣種的賽方基準 OHLCV CSV。

    路徑：
      S3:  s3://{DATA_BUCKET}/baseline/{symbol}USDT_daily_ohlcv.csv
      本機: data/baseline/{symbol}USDT_daily_ohlcv.csv

    回傳：pandas DataFrame（欄位：date, open, high, low, close, volume）
    """
    filename = f"{symbol}USDT_daily_ohlcv.csv"

    if _is_local_mode():
        # 本機 fallback：從 data/baseline/ 讀取
        local_path = _PROJECT_ROOT / "data" / "baseline" / filename
        if not local_path.exists():
            raise FileNotFoundError(
                f"本機基準資料不存在: {local_path}。"
                f"請將 {filename} 放到 data/baseline/ 目錄。"
            )
        df = pd.read_csv(local_path)
    else:
        # S3 模式
        s3 = _get_s3_client()
        key = f"baseline/{filename}"
        response = s3.get_object(Bucket=config.DATA_BUCKET, Key=key)
        body = response["Body"].read()
        df = pd.read_csv(io.BytesIO(body))

    # 確保 date 欄位存在且為字串格式
    if "date" in df.columns:
        df["date"] = df["date"].astype(str)

    return df


def save_raw_payload(run_id, evidence_id, raw_data):
    """把單次外部 API 呼叫的原始回應封存，供主辦方抽查回溯。

    路徑：
      S3:  s3://{DATA_BUCKET}/runs/{run_id}/raw/{evidence_id}.json
      本機: outputs/{run_id}/raw/{evidence_id}.json

    回傳：儲存路徑字串（S3 key 或本地路徑）
    """
    content = json.dumps(raw_data, ensure_ascii=False, default=str)
    relative_key = f"runs/{run_id}/raw/{evidence_id}.json"

    if _is_local_mode():
        local_path = _PROJECT_ROOT / "outputs" / run_id / "raw" / f"{evidence_id}.json"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        return str(local_path)
    else:
        s3 = _get_s3_client()
        s3.put_object(
            Bucket=config.DATA_BUCKET,
            Key=relative_key,
            Body=content.encode("utf-8"),
            ContentType="application/json",
        )
        return relative_key


def save_output_file(run_id, filename, content):
    """把最終交付物（報告、證據清單、執行紀錄）上傳。

    路徑：
      S3:  s3://{DATA_BUCKET}/runs/{run_id}/{filename}
      本機: outputs/{run_id}/{filename}

    回傳：儲存路徑字串（S3 key 或本地路徑）
    """
    relative_key = f"runs/{run_id}/{filename}"

    if _is_local_mode():
        local_path = _PROJECT_ROOT / "outputs" / run_id / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        return str(local_path)
    else:
        s3 = _get_s3_client()
        # 依副檔名設定 Content-Type
        content_type = "application/json"
        if filename.endswith(".md"):
            content_type = "text/markdown; charset=utf-8"
        elif filename.endswith(".jsonl"):
            content_type = "application/x-ndjson"

        s3.put_object(
            Bucket=config.DATA_BUCKET,
            Key=relative_key,
            Body=content.encode("utf-8"),
            ContentType=content_type,
        )
        return relative_key


def generate_download_link(run_id, filename, expires_in=3600):
    """為 S3 上的檔案產生有時效性的下載連結（presigned URL）。

    本機模式時回傳本地檔案的絕對路徑（供開發時直接開啟）。
    S3 模式時產生 presigned URL，預設 1 小時有效。

    回傳：可直接放在網頁上的 https 網址字串，或本地檔案路徑
    """
    relative_key = f"runs/{run_id}/{filename}"

    if _is_local_mode():
        local_path = _PROJECT_ROOT / "outputs" / run_id / filename
        return str(local_path)
    else:
        s3 = _get_s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": config.DATA_BUCKET, "Key": relative_key},
            ExpiresIn=expires_in,
        )
        return url
