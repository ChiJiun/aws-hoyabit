"""S3 讀寫與本機 fallback，包含可重現 JSON 封存。"""

import io
import json
from pathlib import Path

import pandas as pd

import config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REQUIRED_OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume"]

# 舊測試／舊呼叫端曾 patch storage.DATA_BUCKET；sentinel 同時保留
# config.load_local_env() 後動態讀取 config.DATA_BUCKET 的能力。
_CONFIG_BUCKET_SENTINEL = object()
DATA_BUCKET = _CONFIG_BUCKET_SENTINEL


def _data_bucket():
    return config.DATA_BUCKET if DATA_BUCKET is _CONFIG_BUCKET_SENTINEL else DATA_BUCKET


def _is_local_mode():
    return not _data_bucket()


def _get_s3_client():
    import boto3
    return boto3.client("s3", region_name=config.AWS_REGION)


def _safe_segment(value, field_name):
    text = str(value or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError(f"invalid {field_name}: {value!r}")
    return text


def serialize_json_payload(value):
    """以固定 UTF-8 JSON 表示序列化，供檔案內容與 SHA-256 共用。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_ohlcv(df, symbol):
    missing = [column for column in _REQUIRED_OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{symbol} baseline 缺少欄位: {', '.join(missing)}")

    validated = df[_REQUIRED_OHLCV_COLUMNS].copy()
    parsed_dates = pd.to_datetime(validated["date"], errors="coerce", utc=True)
    if parsed_dates.isna().any():
        raise ValueError(f"{symbol} baseline 含無法解析的 date")
    validated["date"] = parsed_dates.dt.strftime("%Y-%m-%d")

    for column in ("open", "high", "low", "close", "volume"):
        validated[column] = pd.to_numeric(validated[column], errors="coerce")
    if validated[["open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError(f"{symbol} baseline 含非數值 OHLCV")
    if validated["date"].duplicated().any():
        validated = validated.drop_duplicates(subset=["date"], keep="last")
    return validated.sort_values("date").reset_index(drop=True)


def read_baseline_csv(symbol):
    """從 S3 或本機讀取 `{SYMBOL}_daily_ohlcv.csv` 並驗證 schema。"""
    symbol_upper = str(symbol).upper().strip()
    if symbol_upper not in config.SUPPORTED_SYMBOLS:
        raise ValueError(f"不支援的 baseline symbol: {symbol}")
    filename = f"{symbol_upper}_daily_ohlcv.csv"

    if _is_local_mode():
        local_path = _PROJECT_ROOT / "data" / "baseline" / filename
        if not local_path.exists():
            raise FileNotFoundError(
                f"本機基準資料不存在: {local_path}。請將 {filename} 放到 data/baseline/ 目錄。"
            )
        df = pd.read_csv(local_path)
    else:
        s3 = _get_s3_client()
        key = f"baseline/{filename}"
        response = s3.get_object(Bucket=_data_bucket(), Key=key)
        df = pd.read_csv(io.BytesIO(response["Body"].read()))

    return _validate_ohlcv(df, symbol_upper)


def save_raw_payload(run_id, evidence_id, raw_data):
    """封存 Evidence envelope，回傳本地路徑或完整 s3:// URI。"""
    safe_run_id = _safe_segment(run_id, "run_id")
    safe_evidence_id = _safe_segment(evidence_id, "evidence_id")
    content = serialize_json_payload(raw_data)
    relative_key = f"runs/{safe_run_id}/raw/{safe_evidence_id}.json"

    if _is_local_mode():
        local_path = _PROJECT_ROOT / "outputs" / safe_run_id / "raw" / f"{safe_evidence_id}.json"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = local_path.with_suffix(".json.tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(local_path)
        return str(local_path)

    s3 = _get_s3_client()
    s3.put_object(
        Bucket=_data_bucket(),
        Key=relative_key,
        Body=content.encode("utf-8"),
        ContentType="application/json",
    )
    return f"s3://{_data_bucket()}/{relative_key}"


def save_output_file(run_id, filename, content):
    """儲存報告、Evidence List 或 Execution Log。"""
    safe_run_id = _safe_segment(run_id, "run_id")
    safe_filename = _safe_segment(filename, "filename")
    relative_key = f"runs/{safe_run_id}/{safe_filename}"

    if _is_local_mode():
        local_path = _PROJECT_ROOT / "outputs" / safe_run_id / safe_filename
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        return str(local_path)

    content_type = "application/json"
    if safe_filename.endswith(".md"):
        content_type = "text/markdown; charset=utf-8"
    elif safe_filename.endswith(".jsonl"):
        content_type = "application/x-ndjson"

    _get_s3_client().put_object(
        Bucket=_data_bucket(),
        Key=relative_key,
        Body=content.encode("utf-8"),
        ContentType=content_type,
    )
    return relative_key


def generate_download_link(run_id, filename, expires_in=3600):
    """產生 S3 presigned URL；本機模式回傳絕對檔案路徑。"""
    safe_run_id = _safe_segment(run_id, "run_id")
    safe_filename = _safe_segment(filename, "filename")
    relative_key = f"runs/{safe_run_id}/{safe_filename}"

    if _is_local_mode():
        return str(_PROJECT_ROOT / "outputs" / safe_run_id / safe_filename)

    return _get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _data_bucket(), "Key": relative_key},
        ExpiresIn=expires_in,
    )
