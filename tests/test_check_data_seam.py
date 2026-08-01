"""
test_check_data_seam.py — check_data_seam 單元測試

驗證基準資料與即時資料接縫校驗邏輯：
- 重疊日期收盤價差異百分比計算
- 通過/警告狀態判定
- 無重疊日期的邊界情境
- execution_log 紀錄
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda", "tools"))

import pandas as pd
import evidence
from tools.price import check_data_seam


def setup_function():
    """每個測試前清空 execution_log。"""
    evidence.reset_stores()


def test_no_overlap_returns_pass():
    """無重疊日期時應回傳 (True, 0, 0.0)。"""
    baseline = pd.DataFrame({
        "date": ["2026-05-29", "2026-05-30", "2026-05-31"],
        "close": [100.0, 101.0, 102.0],
    })
    recent = pd.DataFrame({
        "date": ["2026-06-01", "2026-06-02"],
        "close": [103.0, 104.0],
    })

    passed, overlap_count, max_diff = check_data_seam(baseline, recent)

    assert passed is True
    assert overlap_count == 0
    assert max_diff == 0.0
    # 確認有記入 execution_log
    assert len(evidence.execution_log) == 1
    assert evidence.execution_log[0]["tool_name"] == "check_data_seam"
    assert evidence.execution_log[0]["status"] == "success"


def test_overlap_within_threshold_passes():
    """重疊日期收盤價差異 <= 1% 時應通過。"""
    baseline = pd.DataFrame({
        "date": ["2026-05-30", "2026-05-31"],
        "close": [100.0, 200.0],
    })
    # 差異 0.5% 和 0.3%
    recent = pd.DataFrame({
        "date": ["2026-05-30", "2026-05-31", "2026-06-01"],
        "close": [100.5, 200.6, 201.0],
    })

    passed, overlap_count, max_diff = check_data_seam(baseline, recent)

    assert passed is True
    assert overlap_count == 2
    assert max_diff < 1.0
    assert evidence.execution_log[0]["status"] == "success"


def test_overlap_exceeds_threshold_fails():
    """重疊日期收盤價差異 > 1% 時應回傳不通過。"""
    baseline = pd.DataFrame({
        "date": ["2026-05-30", "2026-05-31"],
        "close": [100.0, 200.0],
    })
    # 差異 5% on first date
    recent = pd.DataFrame({
        "date": ["2026-05-30", "2026-05-31", "2026-06-01"],
        "close": [105.0, 200.0, 201.0],
    })

    passed, overlap_count, max_diff = check_data_seam(baseline, recent)

    assert passed is False
    assert overlap_count == 2
    assert max_diff == 5.0
    assert evidence.execution_log[0]["status"] == "warning"


def test_execution_log_note_contains_info():
    """execution_log 的 note 應包含重疊日數與最大價差。"""
    baseline = pd.DataFrame({
        "date": ["2026-05-31"],
        "close": [100.0],
    })
    recent = pd.DataFrame({
        "date": ["2026-05-31", "2026-06-01"],
        "close": [100.8, 101.0],
    })

    check_data_seam(baseline, recent)

    note = evidence.execution_log[0]["note"]
    assert "重疊日數=1" in note
    assert "最大價差=" in note


def test_baseline_close_zero_skipped():
    """基準收盤價為 0 的日期不應導致除零錯誤。"""
    baseline = pd.DataFrame({
        "date": ["2026-05-30", "2026-05-31"],
        "close": [0.0, 100.0],
    })
    recent = pd.DataFrame({
        "date": ["2026-05-30", "2026-05-31"],
        "close": [50.0, 100.5],
    })

    passed, overlap_count, max_diff = check_data_seam(baseline, recent)

    # 不應拋錯，且只考慮非零基準的日期
    assert overlap_count == 2
    assert max_diff == 0.5  # only 2026-05-31 contributes: (0.5/100)*100 = 0.5%
