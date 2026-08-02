"""Evidence C1 契約與屬性測試。"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from evidence import evidence_list, reset_stores, log_evidence


valid_claim_strategy = st.text(min_size=5, max_size=200).filter(
    lambda value: len(value.strip()) >= 5
)
valid_fetch_result_strategy = st.fixed_dictionaries({
    "schema_version": st.just("1.0"),
    "status": st.just("success"),
    "raw": st.dictionaries(
        st.text(min_size=1, max_size=20),
        st.text(min_size=0, max_size=50),
        max_size=5,
    ),
    "source": st.text(min_size=1, max_size=200),
    "content_reference": st.dictionaries(
        st.text(min_size=1, max_size=20),
        st.text(min_size=0, max_size=50),
        max_size=5,
    ),
    "summary": st.text(min_size=1, max_size=100),
})
run_id_strategy = st.from_regex(r"run_[0-9]{8}_[0-9]{6}", fullmatch=True)
tool_name_strategy = st.sampled_from([
    "get_price_ohlcv", "search_news", "get_onchain",
    "compute_quant", "get_sentiment", "get_macro",
])


def setup_function():
    reset_stores()


@given(
    run_id=run_id_strategy,
    tool_name=tool_name_strategy,
    related_claim=valid_claim_strategy,
    fetch_result=valid_fetch_result_strategy,
)
@settings(max_examples=100)
def test_evidence_record_has_required_and_trace_fields(
    run_id, tool_name, related_claim, fetch_result
):
    reset_stores()
    with patch("storage.save_raw_payload", return_value="s3://bucket/path"):
        result = log_evidence(run_id, tool_name, related_claim, fetch_result)

    assert result.startswith("ev_")
    assert len(evidence_list) == 1
    record = evidence_list[0]
    assert {
        "evidence_id", "source", "fetched_at", "content_reference",
        "related_claim", "tool_name", "raw_payload_path",
        "raw_payload_sha256", "archive_status",
    } <= set(record)
    assert record["evidence_id"] == result
    assert record["source"] == fetch_result["source"]
    assert record["fetched_at"].endswith("Z")
    assert record["content_reference"] == fetch_result["content_reference"]
    assert record["related_claim"] == related_claim
    assert record["archive_status"] == "success"


@given(
    run_id=run_id_strategy,
    tool_name=tool_name_strategy,
    fetch_result=valid_fetch_result_strategy,
    claim=st.one_of(
        st.none(),
        st.just(""),
        st.just("   "),
        st.text(max_size=4).filter(lambda value: len(value.strip()) < 5),
    ),
)
@settings(max_examples=100)
def test_empty_or_short_related_claim_rejected(run_id, tool_name, fetch_result, claim):
    reset_stores()
    with patch("storage.save_raw_payload") as mock_save:
        result = log_evidence(run_id, tool_name, claim, fetch_result)
    assert isinstance(result, dict) and "error" in result
    assert evidence_list == []
    mock_save.assert_not_called()


@given(
    run_id=run_id_strategy,
    tool_names=st.lists(tool_name_strategy, min_size=2, max_size=10),
    claims=st.lists(valid_claim_strategy, min_size=2, max_size=10),
    fetch_results=st.lists(valid_fetch_result_strategy, min_size=2, max_size=10),
)
@settings(max_examples=50)
def test_evidence_ids_are_unique(run_id, tool_names, claims, fetch_results):
    reset_stores()
    n = min(len(tool_names), len(claims), len(fetch_results))
    assume(n >= 2)
    ids = []
    with patch("storage.save_raw_payload", return_value="s3://bucket/path"):
        for index in range(n):
            ids.append(log_evidence(
                run_id, tool_names[index], claims[index], fetch_results[index]
            ))
    assert len(ids) == len(set(ids))
    assert all(evidence_id.startswith("ev_") for evidence_id in ids)


def test_failed_fetch_result_rejected():
    result = log_evidence(
        "run_20260730_141530",
        "get_price_ohlcv",
        "要驗證最近的價格走勢",
        {"status": "error", "error": "API rate limit exceeded"},
    )
    assert isinstance(result, dict) and "error" in result
    assert evidence_list == []


def test_save_raw_payload_receives_full_envelope():
    fetch_result = {
        "schema_version": "1.0",
        "status": "success",
        "raw": {"prices": [100, 200, 300]},
        "source": "https://api.binance.com/api/v3/klines",
        "content_reference": {"pair": "BTCUSDT"},
        "summary": "BTC 日線",
        "anomaly_flags": [{"signal_id": "A5"}],
    }
    with patch("storage.save_raw_payload", return_value="s3://bucket/path") as mock_save:
        evidence_id = log_evidence(
            "run_20260730_141530", "get_price_ohlcv",
            "需要近期價格資料做波動率分析", fetch_result,
        )

    mock_save.assert_called_once()
    run_id, archived_id, envelope = mock_save.call_args.args
    assert run_id == "run_20260730_141530"
    assert archived_id == evidence_id
    assert envelope["raw"] == fetch_result["raw"]
    assert envelope["content_reference"] == fetch_result["content_reference"]
    assert envelope["anomaly_flags"] == fetch_result["anomaly_flags"]
