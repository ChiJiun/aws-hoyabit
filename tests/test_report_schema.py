"""
test_report_schema.py — C7 schema validation, builder, and golden fixture tests.

Covers:
- Three question type golden fixtures (single_integration, hypothesis, comparison)
- C7/Markdown verdict, confidence, signal, and citation consistency
- coverage null/0/59/60/100
- schema validation (required fields, enums, evidence FK, NaN/Inf, date order, 90-day trim)
- Builder/validator/export failure still produces Markdown/Evidence/Log
"""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from report_schema import (
    C7_SCHEMA_VERSION,
    QUESTION_TYPES,
    STANCE_VALUES,
    DIMENSION_STATES,
    SIGNAL_LEVELS,
    MAX_SERIES_DAYS,
    validate_report_data,
    ReportModel,
    build_report_data,
    _confidence_label,
    _normalize_series,
)
from report import generate_report_data, render_report
from export import export_report_data, export_evidence_list, export_execution_log


# ─── Test Helpers ────────────────────────────────────────────────────────────

def make_evidence(eid, source="https://api.binance.com/v3/klines", claim="測試判斷"):
    return {
        "evidence_id": eid,
        "source": source,
        "fetched_at": "2026-07-30T14:15:30Z",
        "content_reference": {"pair": "BTCUSDT"},
        "related_claim": claim,
    }


def _minimal_c7(question_type="single_integration", symbols=None, **overrides):
    """Build a minimal valid C7 dict."""
    symbols = symbols or ["BTC"]
    base = {
        "schema_version": C7_SCHEMA_VERSION,
        "question_type": question_type,
        "symbols": symbols,
        "verdict": {
            "text": "短期偏多",
            "stance": "bullish",
            "confidence": 0.62,
            "confidence_label": "中高",
            "invalidation": "跌破支撐則無效",
        },
        "dimensions": [
            {
                "name": "價格動能",
                "state": "strong",
                "headline": "近兩週 +8.2%",
                "evidence_ids": ["ev_1"],
            }
        ],
        "signals": [],
        "checked_normal": ["帶寬 P54"],
        "hypothesis": None,
        "comparison": None,
        "series": {"price": {"BTC": [["2026-07-01", 60000.0], ["2026-07-30", 65000.0]]}},
        "coverage": {"pct": 86, "got": ["price", "quant"], "missing": []},
        "watchlist": [{"event": "FOMC", "date": "2026-08-18", "why": "利率決議"}],
    }
    base.update(overrides)
    return base



# ═══════════════════════════════════════════════════════════════════════════════
# Golden Fixtures — Three Question Types
# ═══════════════════════════════════════════════════════════════════════════════

SINGLE_ANALYSIS = """
## 市場判斷
BTC 短期偏多，動能強勁。

[VERDICT]
text: BTC 短期偏多，動能強勁
stance: bullish
confidence: 0.72
invalidation: 若跌破 58000 支撐則判斷無效
[/VERDICT]

[DIMENSION]
name: 價格動能
state: strong
headline: 近兩週 +8.2%（波動第74百分位）
evidence_ids: [ev_price]
[/DIMENSION]

[DIMENSION]
name: 技術指標
state: strong
headline: RSI 68, ADX 32 上升趨勢確認
evidence_ids: [ev_quant]
[/DIMENSION]

[DIMENSION]
name: 衍生品
state: na
headline: 資金費率資料不可用
evidence_ids: []
[/DIMENSION]

[SIGNAL]
level: yellow
title: 量價背離
detail: 價格創新高但成交量下降
evidence_ids: [ev_price, ev_quant]
[/SIGNAL]

[CHECKED_NORMAL]
- 帶寬 P54
- 鏈上活躍 ±6%
[/CHECKED_NORMAL]

[COVERAGE]
pct: 75
got: [price, quant]
missing: [derivatives]
[/COVERAGE]

[WATCHLIST]
event: FOMC
date: 2026-08-18
why: 利率決議可能影響風險資產
[/WATCHLIST]

## 關鍵依據
價格數據 [ev_price] 與量化指標 [ev_quant] 顯示動能。

## 信心說明
信心中高，但衍生品資料缺失降低驗證能力。
"""

HYPOTHESIS_ANALYSIS = """
## 市場判斷
假設「ETH 合併後通縮將推升價格」獲得部分支持。

[VERDICT]
text: 假設獲得部分支持但尚不構成強烈結論
stance: neutral
confidence: 0.45
invalidation: 若鏈上通膨率回升則假設失效
[/VERDICT]

[DIMENSION]
name: 鏈上
state: strong
headline: 合併後淨銷毀穩定
evidence_ids: [ev_onchain]
[/DIMENSION]

[DIMENSION]
name: 價格動能
state: weak
headline: 近月 -3% 未反映通縮敘事
evidence_ids: [ev_price]
[/DIMENSION]

[SIGNAL]
level: yellow
title: 敘事與價格脫鉤
detail: 鏈上通縮已確認但價格未反映
evidence_ids: [ev_onchain, ev_price]
[/SIGNAL]

[CHECKED_NORMAL]
- Gas 費率正常
[/CHECKED_NORMAL]

[HYPOTHESIS]
statement: ETH 合併後通縮將推升價格
supporting: [鏈上淨銷毀穩定, 供給減少已確認]
opposing: [價格未反映通縮, 宏觀壓力仍在]
verdict_reason: 供給面支持但需求面尚未配合
[/HYPOTHESIS]

[COVERAGE]
pct: 60
got: [onchain, price, sentiment]
missing: [derivatives]
[/COVERAGE]

[WATCHLIST]
event: Shanghai 升級
date: 2026-09-01
why: 解鎖質押可能改變供需
[/WATCHLIST]

## 關鍵依據
鏈上數據 [ev_onchain] 確認通縮，但價格 [ev_price] 反應冷淡。

## 信心說明
信心中等，假設方向正確但時間尚不確定。
"""

COMPARISON_ANALYSIS = """
## 市場判斷
BTC 在動能維度優於 ETH，但 ETH 在鏈上活躍度領先。

[VERDICT]
text: 短期 BTC 動能較強，但 ETH 有基本面催化劑
stance: mixed
confidence: 0.55
invalidation: BTC 跌破 60000 或 ETH 突破 4000 改變判斷
[/VERDICT]

[DIMENSION]
name: 價格動能
state: strong
headline: BTC +8% vs ETH +2%
evidence_ids: [ev_btc_price, ev_eth_price]
[/DIMENSION]

[DIMENSION]
name: 鏈上
state: strong
headline: ETH 活躍地址增 15%
evidence_ids: [ev_eth_onchain]
[/DIMENSION]

[SIGNAL]
level: red
title: 相關性脫鉤
detail: BTC/ETH 相關性降至 0.6 (近兩年低點)
evidence_ids: [ev_btc_price, ev_eth_price]
[/SIGNAL]

[CHECKED_NORMAL]
- 資金費率兩幣均正常
[/CHECKED_NORMAL]

[COMPARISON]
[ROW]
dimension: 價格動能
edge: A
[/ROW]
[ROW]
dimension: 鏈上活躍度
edge: B
[/ROW]
when_prefer_a: 若追求短期動能且宏觀環境穩定
when_prefer_b: 若看重基本面催化劑與中期潛力
[/COMPARISON]

[COVERAGE]
pct: 80
got: [price, onchain, quant, sentiment]
missing: [derivatives]
[/COVERAGE]

[WATCHLIST]
event: ETH 升級
date: 2026-09-15
why: 可能改變 ETH 鏈上動態
[/WATCHLIST]

## 關鍵依據
BTC 價格 [ev_btc_price]、ETH 價格 [ev_eth_price] 與 ETH 鏈上 [ev_eth_onchain]。

## 信心說明
中等信心，兩幣各有優勢維度。
"""


SINGLE_EVIDENCE = [
    make_evidence("ev_price", "https://api.binance.com/v3/klines"),
    make_evidence("ev_quant", "local_pandas", "計算 BTC 量化指標"),
]

HYPOTHESIS_EVIDENCE = [
    make_evidence("ev_onchain", "https://etherscan.io/api"),
    make_evidence("ev_price", "https://api.binance.com/v3/klines"),
]

COMPARISON_EVIDENCE = [
    make_evidence("ev_btc_price", "https://api.binance.com/v3/klines"),
    make_evidence("ev_eth_price", "https://api.binance.com/v3/klines?symbol=ETHUSDT"),
    make_evidence("ev_eth_onchain", "https://etherscan.io/api"),
]

SAMPLE_SERIES = {
    "price": {
        "BTC": [["2026-07-01", 60000.0], ["2026-07-15", 62000.0], ["2026-07-30", 65000.0]]
    }
}

COMPARISON_SERIES = {
    "price": {
        "BTC": [["2026-07-01", 60000.0], ["2026-07-30", 65000.0]],
        "ETH": [["2026-07-01", 3400.0], ["2026-07-30", 3468.0]],
    }
}



# ═══════════════════════════════════════════════════════════════════════════════
# Test: Three Question Type Golden Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

class TestSingleIntegration:
    """Golden fixture: single_integration question type."""

    def test_builds_valid_c7(self):
        result = build_report_data(
            "single_integration", ["BTC"], SINGLE_ANALYSIS,
            SINGLE_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        assert result["schema_version"] == C7_SCHEMA_VERSION
        assert result["question_type"] == "single_integration"
        assert result["symbols"] == ["BTC"]
        assert result["hypothesis"] is None
        assert result["comparison"] is None

    def test_verdict_fields(self):
        result = build_report_data(
            "single_integration", ["BTC"], SINGLE_ANALYSIS,
            SINGLE_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        v = result["verdict"]
        assert v["stance"] == "bullish"
        assert 0 <= v["confidence"] <= 1
        assert v["confidence_label"] in ("低", "中等", "中高", "高")
        assert v["invalidation"]

    def test_dimensions_include_na_state(self):
        result = build_report_data(
            "single_integration", ["BTC"], SINGLE_ANALYSIS,
            SINGLE_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        states = [d["state"] for d in result["dimensions"]]
        assert "na" in states  # 衍生品缺資料

    def test_signals_present(self):
        result = build_report_data(
            "single_integration", ["BTC"], SINGLE_ANALYSIS,
            SINGLE_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        assert len(result["signals"]) >= 1
        assert result["signals"][0]["level"] in SIGNAL_LEVELS

    def test_coverage_values(self):
        result = build_report_data(
            "single_integration", ["BTC"], SINGLE_ANALYSIS,
            SINGLE_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        cov = result["coverage"]
        assert cov["pct"] is not None
        assert 0 <= cov["pct"] <= 100
        assert isinstance(cov["got"], list)
        assert isinstance(cov["missing"], list)

    def test_validates_cleanly(self):
        result = build_report_data(
            "single_integration", ["BTC"], SINGLE_ANALYSIS,
            SINGLE_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        known_ids = {e["evidence_id"] for e in SINGLE_EVIDENCE}
        errors = validate_report_data(result, evidence_ids=known_ids)
        assert errors == []


class TestHypothesis:
    """Golden fixture: hypothesis question type."""

    def test_builds_valid_c7(self):
        result = build_report_data(
            "hypothesis", ["ETH"], HYPOTHESIS_ANALYSIS,
            HYPOTHESIS_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        assert result["question_type"] == "hypothesis"
        assert result["symbols"] == ["ETH"]
        assert result["comparison"] is None

    def test_hypothesis_block_present(self):
        result = build_report_data(
            "hypothesis", ["ETH"], HYPOTHESIS_ANALYSIS,
            HYPOTHESIS_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        hyp = result["hypothesis"]
        assert isinstance(hyp, dict)
        assert "statement" in hyp
        assert "supporting" in hyp
        assert "opposing" in hyp
        assert "verdict_reason" in hyp

    def test_verdict_stance_neutral(self):
        result = build_report_data(
            "hypothesis", ["ETH"], HYPOTHESIS_ANALYSIS,
            HYPOTHESIS_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        assert result["verdict"]["stance"] == "neutral"

    def test_validates_cleanly(self):
        result = build_report_data(
            "hypothesis", ["ETH"], HYPOTHESIS_ANALYSIS,
            HYPOTHESIS_EVIDENCE, series=SAMPLE_SERIES,
        )
        assert result is not None
        known_ids = {e["evidence_id"] for e in HYPOTHESIS_EVIDENCE}
        errors = validate_report_data(result, evidence_ids=known_ids)
        assert errors == []


class TestComparison:
    """Golden fixture: comparison question type."""

    def test_builds_valid_c7(self):
        result = build_report_data(
            "comparison", ["BTC", "ETH"], COMPARISON_ANALYSIS,
            COMPARISON_EVIDENCE, series=COMPARISON_SERIES,
        )
        assert result is not None
        assert result["question_type"] == "comparison"
        assert result["symbols"] == ["BTC", "ETH"]
        assert result["hypothesis"] is None

    def test_comparison_block_present(self):
        result = build_report_data(
            "comparison", ["BTC", "ETH"], COMPARISON_ANALYSIS,
            COMPARISON_EVIDENCE, series=COMPARISON_SERIES,
        )
        assert result is not None
        comp = result["comparison"]
        assert isinstance(comp, dict)
        assert "rows" in comp
        assert "when_prefer_a" in comp
        assert "when_prefer_b" in comp

    def test_red_signal_present(self):
        result = build_report_data(
            "comparison", ["BTC", "ETH"], COMPARISON_ANALYSIS,
            COMPARISON_EVIDENCE, series=COMPARISON_SERIES,
        )
        assert result is not None
        levels = [s["level"] for s in result["signals"]]
        assert "red" in levels

    def test_validates_cleanly(self):
        result = build_report_data(
            "comparison", ["BTC", "ETH"], COMPARISON_ANALYSIS,
            COMPARISON_EVIDENCE, series=COMPARISON_SERIES,
        )
        assert result is not None
        known_ids = {e["evidence_id"] for e in COMPARISON_EVIDENCE}
        errors = validate_report_data(result, evidence_ids=known_ids)
        assert errors == []



# ═══════════════════════════════════════════════════════════════════════════════
# Test: validate_report_data edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidation:
    """C7 validator unit tests."""

    def test_valid_minimal_single(self):
        data = _minimal_c7()
        errors = validate_report_data(data, evidence_ids={"ev_1"})
        assert errors == []

    def test_not_a_dict(self):
        errors = validate_report_data("not a dict")
        assert len(errors) == 1
        assert errors[0]["code"] == "type"

    def test_missing_required_fields(self):
        errors = validate_report_data({})
        assert len(errors) == 10  # one per C7_REQUIRED_FIELDS
        assert all(e["code"] == "required" for e in errors)

    def test_wrong_schema_version(self):
        data = _minimal_c7(schema_version="2.0")
        errors = validate_report_data(data)
        assert any(e["path"] == "$.schema_version" for e in errors)

    def test_invalid_question_type(self):
        data = _minimal_c7(question_type="invalid")
        errors = validate_report_data(data)
        assert any(e["code"] == "enum" and "question_type" in e["path"] for e in errors)

    def test_invalid_stance(self):
        data = _minimal_c7()
        data["verdict"]["stance"] = "very_bullish"
        errors = validate_report_data(data)
        assert any("stance" in e["path"] for e in errors)

    def test_confidence_out_of_range(self):
        data = _minimal_c7()
        data["verdict"]["confidence"] = 1.5
        errors = validate_report_data(data)
        assert any("confidence" in e["path"] and e["code"] == "range" for e in errors)

    def test_confidence_nan(self):
        data = _minimal_c7()
        data["verdict"]["confidence"] = float("nan")
        errors = validate_report_data(data)
        assert any("confidence" in e["path"] for e in errors)

    def test_confidence_negative(self):
        data = _minimal_c7()
        data["verdict"]["confidence"] = -0.1
        errors = validate_report_data(data)
        assert any("confidence" in e["path"] for e in errors)

    def test_symbols_count_single(self):
        data = _minimal_c7(symbols=["BTC", "ETH"])  # single but 2 symbols
        errors = validate_report_data(data)
        assert any("symbols" in e["path"] and e["code"] == "length" for e in errors)

    def test_symbols_count_comparison(self):
        data = _minimal_c7(question_type="comparison", symbols=["BTC"])
        data["comparison"] = {"rows": [], "when_prefer_a": "", "when_prefer_b": ""}
        data["hypothesis"] = None
        errors = validate_report_data(data)
        assert any("symbols" in e["path"] and e["code"] == "length" for e in errors)

    def test_dimension_invalid_state(self):
        data = _minimal_c7()
        data["dimensions"][0]["state"] = "very_strong"
        errors = validate_report_data(data)
        assert any("state" in e["path"] and e["code"] == "enum" for e in errors)

    def test_signal_invalid_level(self):
        data = _minimal_c7()
        data["signals"] = [{"level": "green", "title": "x", "detail": "y", "evidence_ids": []}]
        errors = validate_report_data(data)
        assert any("level" in e["path"] for e in errors)

    def test_evidence_ids_fk_missing(self):
        data = _minimal_c7()
        data["dimensions"][0]["evidence_ids"] = ["ev_1", "ev_ghost"]
        errors = validate_report_data(data, evidence_ids={"ev_1"})
        assert any(e["code"] == "fk" and "ev_ghost" in e["message"] for e in errors)

    def test_evidence_ids_fk_no_check_without_known_ids(self):
        """When evidence_ids param is None, FK check is skipped."""
        data = _minimal_c7()
        data["dimensions"][0]["evidence_ids"] = ["ev_ghost"]
        errors = validate_report_data(data, evidence_ids=None)
        assert not any(e["code"] == "fk" for e in errors)

    def test_series_nan_value(self):
        data = _minimal_c7()
        data["series"] = {"price": {"BTC": [["2026-07-01", float("nan")]]}}
        errors = validate_report_data(data)
        assert any(e["code"] == "finite" for e in errors)

    def test_series_inf_value(self):
        data = _minimal_c7()
        data["series"] = {"price": {"BTC": [["2026-07-01", float("inf")]]}}
        errors = validate_report_data(data)
        assert any(e["code"] == "finite" for e in errors)

    def test_series_date_order(self):
        data = _minimal_c7()
        data["series"] = {"price": {"BTC": [["2026-07-30", 1.0], ["2026-07-01", 2.0]]}}
        errors = validate_report_data(data)
        assert any(e["code"] == "order" for e in errors)

    def test_series_exceeds_90_days(self):
        data = _minimal_c7()
        data["series"] = {"price": {"BTC": [["2026-01-01", 1.0], ["2026-07-30", 2.0]]}}
        errors = validate_report_data(data)
        assert any(e["code"] == "span" for e in errors)

    def test_series_invalid_date(self):
        data = _minimal_c7()
        data["series"] = {"price": {"BTC": [["not-a-date", 1.0]]}}
        errors = validate_report_data(data)
        assert any(e["code"] == "date" for e in errors)

    def test_hypothesis_required_for_hypothesis_type(self):
        data = _minimal_c7(question_type="hypothesis", symbols=["ETH"])
        data["hypothesis"] = None
        errors = validate_report_data(data)
        assert any("hypothesis" in e["path"] and e["code"] == "required" for e in errors)

    def test_comparison_required_for_comparison_type(self):
        data = _minimal_c7(question_type="comparison", symbols=["BTC", "ETH"])
        data["comparison"] = None
        errors = validate_report_data(data)
        assert any("comparison" in e["path"] and e["code"] == "required" for e in errors)

    def test_hypothesis_must_be_null_for_single(self):
        data = _minimal_c7()
        data["hypothesis"] = {"statement": "x", "supporting": [], "opposing": [], "verdict_reason": "y"}
        errors = validate_report_data(data)
        assert any("hypothesis" in e["path"] and e["code"] == "null_expected" for e in errors)

    def test_comparison_must_be_null_for_hypothesis(self):
        data = _minimal_c7(question_type="hypothesis", symbols=["ETH"])
        data["hypothesis"] = {"statement": "x", "supporting": [], "opposing": [], "verdict_reason": "y"}
        data["comparison"] = {"rows": [], "when_prefer_a": "", "when_prefer_b": ""}
        errors = validate_report_data(data)
        assert any("comparison" in e["path"] and e["code"] == "null_expected" for e in errors)

    def test_coverage_pct_null_is_valid(self):
        data = _minimal_c7()
        data["coverage"] = {"pct": None, "got": [], "missing": []}
        errors = validate_report_data(data)
        assert not any("coverage.pct" in e["path"] for e in errors)

    def test_coverage_pct_zero_is_valid(self):
        data = _minimal_c7()
        data["coverage"] = {"pct": 0, "got": [], "missing": [{"capability": "x", "reason": "y"}]}
        errors = validate_report_data(data)
        assert not any("coverage.pct" in e["path"] for e in errors)

    def test_coverage_pct_100_is_valid(self):
        data = _minimal_c7()
        data["coverage"] = {"pct": 100, "got": ["all"], "missing": []}
        errors = validate_report_data(data)
        assert not any("coverage.pct" in e["path"] for e in errors)

    def test_coverage_pct_out_of_range(self):
        data = _minimal_c7()
        data["coverage"] = {"pct": 101, "got": [], "missing": []}
        errors = validate_report_data(data)
        assert any("coverage.pct" in e["path"] for e in errors)

    def test_unknown_extension_fields_are_tolerated(self):
        """Extension fields don't cause validation failure (forward compat)."""
        data = _minimal_c7()
        data["custom_extension"] = {"foo": "bar"}
        data["verdict"]["extra_note"] = "some note"
        errors = validate_report_data(data, evidence_ids={"ev_1"})
        assert errors == []

    def test_signal_metric_nan_rejected(self):
        data = _minimal_c7()
        data["signals"] = [{
            "level": "yellow",
            "title": "test",
            "detail": "detail",
            "evidence_ids": [],
            "metrics": [{"label": "x", "value": float("nan"), "percentile": 50}],
        }]
        errors = validate_report_data(data)
        assert any(e["code"] == "finite" and "metrics" in e["path"] for e in errors)

    def test_signal_metric_inf_percentile_rejected(self):
        data = _minimal_c7()
        data["signals"] = [{
            "level": "red",
            "title": "test",
            "detail": "detail",
            "evidence_ids": [],
            "metrics": [{"label": "x", "value": 1.0, "percentile": float("inf")}],
        }]
        errors = validate_report_data(data)
        assert any(e["code"] == "finite" and "percentile" in e["path"] for e in errors)



# ═══════════════════════════════════════════════════════════════════════════════
# Test: Coverage boundary (null, 0, 59, 60, 100)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCoverageBoundary:
    """coverage.pct semantics: only Phase A capability availability."""

    def test_coverage_null_when_no_capabilities(self):
        """No applicable capabilities → pct is null."""
        analysis = """
[VERDICT]
text: test
stance: neutral
confidence: 0.5
invalidation: none
[/VERDICT]

[COVERAGE]
pct: null
got: []
missing: []
[/COVERAGE]

[CHECKED_NORMAL]
- nothing
[/CHECKED_NORMAL]

[WATCHLIST]
event: test
date: 2026-08-01
why: test
[/WATCHLIST]
"""
        result = build_report_data("single_integration", ["BTC"], analysis, [], series={})
        # Either returns valid data with null pct or None (no dims/signals to validate)
        if result is not None:
            assert result["coverage"]["pct"] is None

    def test_coverage_zero(self):
        """All capabilities failed → pct = 0."""
        data = _minimal_c7()
        data["coverage"] = {
            "pct": 0,
            "got": [],
            "missing": [{"capability": "price", "reason": "timeout"}, {"capability": "quant", "reason": "error"}],
        }
        errors = validate_report_data(data, evidence_ids={"ev_1"})
        assert not any("coverage" in e["path"] for e in errors)

    def test_coverage_59_below_threshold(self):
        """pct=59 is valid; warning threshold at 60 does not reject."""
        data = _minimal_c7()
        data["coverage"]["pct"] = 59
        errors = validate_report_data(data, evidence_ids={"ev_1"})
        assert not any("coverage.pct" in e["path"] for e in errors)

    def test_coverage_60_at_threshold(self):
        """pct=60 is valid; at warning boundary."""
        data = _minimal_c7()
        data["coverage"]["pct"] = 60
        errors = validate_report_data(data, evidence_ids={"ev_1"})
        assert not any("coverage.pct" in e["path"] for e in errors)

    def test_coverage_100_full(self):
        """pct=100 means all Phase A capabilities succeeded."""
        data = _minimal_c7()
        data["coverage"]["pct"] = 100
        errors = validate_report_data(data, evidence_ids={"ev_1"})
        assert not any("coverage.pct" in e["path"] for e in errors)

    def test_coverage_is_not_dimension_score(self):
        """coverage.pct is only data availability, NOT a dimension/quality score."""
        data = _minimal_c7()
        # Even with max coverage, dimensions can still be "na"
        data["coverage"]["pct"] = 100
        data["dimensions"] = [
            {"name": "衍生品", "state": "na", "headline": "不適用", "evidence_ids": []},
        ]
        errors = validate_report_data(data, evidence_ids={"ev_1"})
        # This is perfectly valid - high coverage doesn't force strong dimensions
        assert not any("dimensions" in e["path"] and e["code"] == "enum" for e in errors)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Graceful Failure — Builder/Validator/Export don't block deliverables
# ═══════════════════════════════════════════════════════════════════════════════

class TestGracefulFailure:
    """build_report_data failure must not block Markdown/Evidence/Log output."""

    def test_invalid_question_type_returns_none(self):
        log = []
        result = build_report_data("invalid_type", ["BTC"], "text", [], execution_log=log)
        assert result is None
        assert any("error" in entry.get("status", "") for entry in log)

    def test_empty_analysis_returns_none_or_minimal(self):
        """No structured markers → either returns None (validation fail) or minimal valid C7."""
        log = []
        result = build_report_data("single_integration", ["BTC"], "", [], execution_log=log)
        if result is not None:
            # If it succeeds, it must still be valid C7
            errors = validate_report_data(result)
            assert errors == []
        # Either way, no exception was raised

    def test_none_inputs_returns_none(self):
        log = []
        result = build_report_data("single_integration", None, None, None, execution_log=log)
        assert result is None

    def test_markdown_still_works_when_c7_fails(self):
        """render_report continues even if C7 would fail."""
        evidence = [make_evidence("ev_1", "https://binance.com/api")]
        # Render report (original deliverable) succeeds independently
        md = render_report("run_1", "測試", "分析文字 [ev_1]", evidence)
        assert "## 市場判斷" in md
        assert "## 關鍵依據" in md
        assert "## 信心說明" in md

    def test_evidence_export_independent_of_c7(self):
        """Evidence export works regardless of C7 status."""
        evidence = [make_evidence("ev_1", "https://binance.com")]
        json_str = export_evidence_list(evidence)
        parsed = json.loads(json_str)
        assert len(parsed) == 1
        assert parsed[0]["evidence_id"] == "ev_1"

    def test_execution_log_export_independent_of_c7(self):
        """Execution log export works regardless of C7 status."""
        log = [
            {"tool_name": "test", "status": "success", "elapsed_ms": 100},
            {"tool_name": "build_report_data", "status": "error", "note": "C7 failed"},
        ]
        jsonl = export_execution_log(log)
        lines = [l for l in jsonl.strip().split("\n") if l]
        assert len(lines) == 2
        assert json.loads(lines[1])["status"] == "error"

    def test_export_report_data_none_returns_none(self):
        """export_report_data with None input returns None."""
        assert export_report_data(None) is None

    def test_export_report_data_valid_dict(self):
        """export_report_data serializes valid C7 to JSON string."""
        data = _minimal_c7()
        result = export_report_data(data)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["schema_version"] == C7_SCHEMA_VERSION

    def test_generate_report_data_wrapper_catches_all(self):
        """generate_report_data (report.py wrapper) never raises."""
        log = []
        # Pass completely invalid inputs
        result = generate_report_data("bad", [], "", None, execution_log=log)
        assert result is None
        # The execution_log should have an error entry
        assert len(log) >= 1



# ═══════════════════════════════════════════════════════════════════════════════
# Test: Series normalization (90-day trim, dedup, ascending, finite)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeriesNormalization:
    """_normalize_series handles edge cases properly."""

    def test_sorts_ascending(self):
        series = {"price": {"BTC": [["2026-07-30", 2.0], ["2026-07-01", 1.0]]}}
        result = _normalize_series(series)
        assert result["price"]["BTC"][0][0] == "2026-07-01"
        assert result["price"]["BTC"][1][0] == "2026-07-30"

    def test_deduplicates_dates(self):
        series = {"price": {"BTC": [["2026-07-01", 1.0], ["2026-07-01", 2.0], ["2026-07-02", 3.0]]}}
        result = _normalize_series(series)
        dates = [p[0] for p in result["price"]["BTC"]]
        assert len(dates) == len(set(dates))

    def test_trims_to_90_days(self):
        # 120 days of data
        points = [[f"2026-{(4 + i // 30):02d}-{(i % 30) + 1:02d}", float(i)] for i in range(120)]
        # Fix to use valid dates
        from datetime import date, timedelta
        start = date(2026, 4, 1)
        points = [[(start + timedelta(days=i)).isoformat(), float(i)] for i in range(120)]
        series = {"price": {"BTC": points}}
        result = _normalize_series(series)
        if result.get("price", {}).get("BTC"):
            pts = result["price"]["BTC"]
            from report_schema import _parse_date
            first_d = _parse_date(pts[0][0])
            last_d = _parse_date(pts[-1][0])
            assert (last_d - first_d).days <= MAX_SERIES_DAYS

    def test_removes_nan_values(self):
        series = {"price": {"BTC": [["2026-07-01", float("nan")], ["2026-07-02", 100.0]]}}
        result = _normalize_series(series)
        assert len(result["price"]["BTC"]) == 1
        assert result["price"]["BTC"][0][1] == 100.0

    def test_removes_inf_values(self):
        series = {"price": {"BTC": [["2026-07-01", float("inf")], ["2026-07-02", 100.0]]}}
        result = _normalize_series(series)
        assert len(result["price"]["BTC"]) == 1

    def test_removes_invalid_dates(self):
        series = {"price": {"BTC": [["not-a-date", 1.0], ["2026-07-02", 2.0]]}}
        result = _normalize_series(series)
        assert len(result["price"]["BTC"]) == 1
        assert result["price"]["BTC"][0][0] == "2026-07-02"

    def test_empty_series_returns_empty(self):
        assert _normalize_series({}) == {}
        assert _normalize_series(None) == {}

    def test_non_list_points_skipped(self):
        series = {"price": {"BTC": "not a list"}}
        result = _normalize_series(series)
        assert result == {"price": {}}


# ═══════════════════════════════════════════════════════════════════════════════
# Test: ReportModel
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportModel:
    """ReportModel as single intermediate model."""

    def test_to_report_data_has_all_required_fields(self):
        model = ReportModel(
            question_type="single_integration",
            symbols=["BTC"],
            verdict_text="test",
            stance="bullish",
            confidence=0.7,
            invalidation="break support",
            dimensions=[{"name": "價格", "state": "strong", "headline": "up", "evidence_ids": []}],
            signals=[],
            checked_normal=["ok"],
            series={"price": {"BTC": [["2026-07-30", 100.0]]}},
            coverage={"pct": 80, "got": ["price"], "missing": []},
            watchlist=[],
        )
        data = model.to_report_data()
        from report_schema import C7_REQUIRED_FIELDS
        for field in C7_REQUIRED_FIELDS:
            assert field in data

    def test_invalid_stance_defaults_to_neutral(self):
        model = ReportModel(question_type="single_integration", symbols=["BTC"], stance="super_bullish")
        assert model.stance == "neutral"

    def test_non_finite_confidence_defaults(self):
        model = ReportModel(question_type="single_integration", symbols=["BTC"], confidence=float("nan"))
        assert model.confidence == 0.5

    def test_confidence_label_auto_derived(self):
        model = ReportModel(question_type="single_integration", symbols=["BTC"], confidence=0.75)
        assert model.confidence_label == "中高"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Confidence label utility
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfidenceLabel:
    def test_low(self):
        assert _confidence_label(0.1) == "低"
        assert _confidence_label(0.29) == "低"

    def test_medium(self):
        assert _confidence_label(0.3) == "中等"
        assert _confidence_label(0.59) == "中等"

    def test_medium_high(self):
        assert _confidence_label(0.6) == "中高"
        assert _confidence_label(0.79) == "中高"

    def test_high(self):
        assert _confidence_label(0.8) == "高"
        assert _confidence_label(1.0) == "高"
