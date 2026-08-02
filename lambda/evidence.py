"""Evidence 記錄、品質資訊與原始資料封存索引。"""

import hashlib
import uuid
from datetime import datetime, timezone

import storage

# 執行期間累積證據與日誌的容器。每次執行開始時由 reset_stores() 清空。
evidence_list = []
execution_log = []


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reset_stores():
    """清空上一次 Lambda 容器可能殘留的證據與執行紀錄。"""
    evidence_list.clear()
    execution_log.clear()


def log_evidence(run_id, tool_name, related_claim, fetch_result):
    """把成功工具結果轉成可回溯 Evidence 並封存完整 envelope。

    命題必要欄位 `source`、`fetched_at`、`content_reference`、
    `related_claim` 永遠保留；額外欄位提供工具、品質、異常、封存位置與
    SHA-256，供抽查和完整性驗證。
    """
    if not related_claim or len(str(related_claim).strip()) < 5:
        return {"error": "related_claim is empty or too short"}
    if not isinstance(fetch_result, dict):
        return {"error": "fetch_result must be a dict"}
    if fetch_result.get("error") or fetch_result.get("status") == "error":
        return {"error": "failed tool result cannot be recorded as evidence"}

    evidence_id = f"ev_{uuid.uuid4()}"
    fetched_at = _utc_now()
    source = fetch_result.get("source", "unknown")
    # 防禦性轉型：工具若回傳非預期型別，不得讓 dict()/list() 拋出例外中斷整次執行
    raw_reference = fetch_result.get("content_reference")
    content_reference = dict(raw_reference) if isinstance(raw_reference, dict) else {}
    raw_flags = fetch_result.get("anomaly_flags")
    anomaly_flags = list(raw_flags) if isinstance(raw_flags, (list, tuple)) else []
    raw_quality = content_reference.get("quality")
    data_quality = dict(raw_quality) if isinstance(raw_quality, dict) else {}

    envelope = {
        "schema_version": fetch_result.get("schema_version", "1.0"),
        "evidence_id": evidence_id,
        "run_id": run_id,
        "tool_name": tool_name,
        "source": source,
        "fetched_at": fetched_at,
        "related_claim": str(related_claim),
        "content_reference": content_reference,
        "anomaly_flags": anomaly_flags,
        "raw": fetch_result.get("raw", {}),
    }
    serialized = storage.serialize_json_payload(envelope).encode("utf-8")
    raw_payload_sha256 = hashlib.sha256(serialized).hexdigest()

    raw_payload_path = None
    archive_status = "success"
    archive_error = None
    try:
        raw_payload_path = storage.save_raw_payload(run_id, evidence_id, envelope)
    except Exception as exc:  # Evidence 本身仍保留，但清楚標示封存失敗。
        archive_status = "failed"
        archive_error = f"{type(exc).__name__}: {exc}"
        log_execution_step(
            "save_raw_payload",
            "error",
            0,
            evidence_id=evidence_id,
            note=archive_error,
        )

    source_url = source if isinstance(source, str) and source.startswith(("http://", "https://")) else None
    record = {
        "evidence_id": evidence_id,
        "source": source,
        "fetched_at": fetched_at,
        "content_reference": content_reference,
        "related_claim": str(related_claim),
        "schema_version": fetch_result.get("schema_version", "1.0"),
        "tool_name": tool_name,
        "source_url": source_url,
        "data_quality": data_quality,
        "anomaly_flags": anomaly_flags,
        "raw_payload_path": raw_payload_path,
        "raw_payload_sha256": raw_payload_sha256,
        "archive_status": archive_status,
        "archive_error": archive_error,
    }
    evidence_list.append(record)
    return evidence_id


def log_execution_step(tool_name, status, elapsed_ms, evidence_id=None, note=None):
    """記錄成功、失敗、降級或限制，供 Execution Log 與報告限制使用。"""
    record = {
        "timestamp": _utc_now(),
        "tool_name": tool_name,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "evidence_id": evidence_id,
        "note": note,
    }
    execution_log.append(record)
