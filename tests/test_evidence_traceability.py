import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import evidence
import export
import storage


def _tool_result():
    return {
        "schema_version": "1.0",
        "status": "success",
        "raw": {"price": 100},
        "source": "https://api.example.test/price",
        "summary": "BTC price 100",
        "content_reference": {
            "provider": "Example",
            "quality": {"freshness": {"status": "fresh"}},
        },
        "anomaly_flags": [{"signal_id": "A5"}],
    }


def setup_function():
    evidence.reset_stores()


def test_log_evidence_archives_full_envelope_and_hash():
    captured = {}

    def save(run_id, evidence_id, envelope):
        captured["run_id"] = run_id
        captured["evidence_id"] = evidence_id
        captured["envelope"] = envelope
        return f"s3://bucket/runs/{run_id}/raw/{evidence_id}.json"

    with patch("storage.save_raw_payload", side_effect=save):
        evidence_id = evidence.log_evidence(
            "run_001", "get_price_ohlcv", "驗證 BTC 價格趨勢", _tool_result()
        )

    record = evidence.evidence_list[0]
    assert evidence_id.startswith("ev_")
    assert captured["envelope"]["raw"] == {"price": 100}
    assert captured["envelope"]["content_reference"]["provider"] == "Example"
    expected_hash = hashlib.sha256(
        storage.serialize_json_payload(captured["envelope"]).encode("utf-8")
    ).hexdigest()
    assert record["raw_payload_sha256"] == expected_hash
    assert record["raw_payload_path"].startswith("s3://")
    assert record["archive_status"] == "success"
    assert record["source_url"] == "https://api.example.test/price"
    assert record["data_quality"]["freshness"]["status"] == "fresh"


def test_archive_failure_is_visible_without_losing_evidence():
    with patch("storage.save_raw_payload", side_effect=OSError("disk full")):
        evidence_id = evidence.log_evidence(
            "run_001", "get_price_ohlcv", "驗證 BTC 價格趨勢", _tool_result()
        )
    assert evidence_id.startswith("ev_")
    record = evidence.evidence_list[0]
    assert record["archive_status"] == "failed"
    assert "disk full" in record["archive_error"]
    assert any(step["tool_name"] == "save_raw_payload" for step in evidence.execution_log)


def test_failed_tool_result_is_not_logged_as_evidence():
    result = evidence.log_evidence(
        "run_001", "get_price_ohlcv", "驗證 BTC 價格趨勢",
        {"status": "error", "error": "timeout"},
    )
    assert "error" in result
    assert evidence.evidence_list == []


def test_export_preserves_traceability_fields():
    with patch("storage.save_raw_payload", return_value="local/path.json"):
        evidence.log_evidence(
            "run_001", "get_price_ohlcv", "驗證 BTC 價格趨勢", _tool_result()
        )
    exported = json.loads(export.export_evidence_list(evidence.evidence_list))
    assert exported[0]["tool_name"] == "get_price_ohlcv"
    assert exported[0]["raw_payload_sha256"]
    assert exported[0]["archive_status"] == "success"
    assert exported[0]["anomaly_flags"] == [{"signal_id": "A5"}]
