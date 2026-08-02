"""
test_series_utils.py — 測試 series_utils 共用序列處理工具

涵蓋：日期錯位、時區、重複、NaN/Inf、零分母、91日裁切、inner join、relative strength
"""

import math
import sys
from pathlib import Path

# 確保 lambda/ 在 Python path 上
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from tools.series_utils import (
    normalize_series,
    build_series_envelope,
    extract_price_series,
    inner_join_series,
    calc_relative_strength,
)


# ============================================================
# normalize_series
# ============================================================

class TestNormalizeSeries:
    """核心正規化邏輯測試。"""

    def test_empty_input(self):
        assert normalize_series([]) == []
        assert normalize_series(None) == []

    def test_basic_sorting_ascending(self):
        points = [["2026-07-03", 100], ["2026-07-01", 98], ["2026-07-02", 99]]
        result = normalize_series(points)
        dates = [p[0] for p in result]
        assert dates == ["2026-07-01", "2026-07-02", "2026-07-03"]

    def test_dedup_keeps_last(self):
        points = [
            ["2026-07-01", 100],
            ["2026-07-01", 101],  # duplicate date, should keep this
            ["2026-07-02", 102],
        ]
        result = normalize_series(points)
        assert len(result) == 2
        assert result[0] == ["2026-07-01", 101.0]
        assert result[1] == ["2026-07-02", 102.0]

    def test_filters_nan(self):
        points = [
            ["2026-07-01", 100],
            ["2026-07-02", float("nan")],
            ["2026-07-03", 102],
        ]
        result = normalize_series(points)
        assert len(result) == 2
        assert result[0][0] == "2026-07-01"
        assert result[1][0] == "2026-07-03"

    def test_filters_inf(self):
        points = [
            ["2026-07-01", 100],
            ["2026-07-02", float("inf")],
            ["2026-07-03", float("-inf")],
            ["2026-07-04", 103],
        ]
        result = normalize_series(points)
        assert len(result) == 2

    def test_filters_none_value(self):
        points = [
            ["2026-07-01", 100],
            ["2026-07-02", None],
            ["2026-07-03", 102],
        ]
        result = normalize_series(points)
        assert len(result) == 2

    def test_91_day_trim(self):
        """91 日資料裁切到 90 筆。"""
        points = [[f"2026-{(i // 28) + 4:02d}-{(i % 28) + 1:02d}", float(i)]
                  for i in range(91)]
        # Generate proper 91 consecutive dates
        from datetime import date, timedelta
        base = date(2026, 5, 1)
        points = [[(base + timedelta(days=i)).isoformat(), float(i)] for i in range(91)]
        result = normalize_series(points, max_days=90)
        assert len(result) == 90
        # Should keep most recent 90, dropping the earliest
        assert result[0][0] == (base + timedelta(days=1)).isoformat()

    def test_timezone_normalization(self):
        """不同時區的日期應正規化為 UTC 日期字串。"""
        points = [
            ["2026-07-01T23:00:00+08:00", 100],  # UTC: 2026-07-01 15:00
            ["2026-07-02T01:00:00-05:00", 101],  # UTC: 2026-07-02 06:00
            ["2026-07-03T00:00:00Z", 102],
        ]
        result = normalize_series(points)
        assert len(result) == 3
        assert result[0][0] == "2026-07-01"
        assert result[1][0] == "2026-07-02"
        assert result[2][0] == "2026-07-03"

    def test_invalid_date_skipped(self):
        points = [
            ["2026-07-01", 100],
            ["not-a-date", 101],
            ["2026-07-03", 102],
        ]
        result = normalize_series(points)
        assert len(result) == 2

    def test_max_days_none_keeps_all(self):
        from datetime import date, timedelta
        base = date(2026, 1, 1)
        points = [[(base + timedelta(days=i)).isoformat(), float(i)] for i in range(200)]
        result = normalize_series(points, max_days=None)
        assert len(result) == 200

    def test_all_values_finite_in_output(self):
        """Property: all output values must be finite floats."""
        import random
        random.seed(42)
        points = []
        from datetime import date, timedelta
        base = date(2026, 1, 1)
        for i in range(100):
            d = (base + timedelta(days=i)).isoformat()
            # Mix of valid and invalid values
            val = random.choice([100.0, float("nan"), float("inf"), None, 50.0, -10.0])
            points.append([d, val])
        result = normalize_series(points)
        for _, val in result:
            assert isinstance(val, float)
            assert math.isfinite(val)

    def test_dates_strictly_increasing(self):
        """Property: output dates must be strictly increasing."""
        from datetime import date, timedelta
        base = date(2026, 3, 1)
        points = [[(base + timedelta(days=i)).isoformat(), float(i * 10)] for i in range(50)]
        # Add duplicates
        points.append(["2026-03-05", 999.0])
        points.append(["2026-03-10", 888.0])
        result = normalize_series(points)
        for i in range(1, len(result)):
            assert result[i][0] > result[i - 1][0]



# ============================================================
# build_series_envelope
# ============================================================

class TestBuildSeriesEnvelope:
    def test_basic_envelope(self):
        points = [["2026-07-01", 100.0], ["2026-07-02", 101.0]]
        env = build_series_envelope(
            points, unit="USD", provider="Binance", pair="BTCUSDT"
        )
        assert env["points"] == points
        assert env["unit"] == "USD"
        assert env["provider"] == "Binance"
        assert env["pair"] == "BTCUSDT"
        assert env["timeframe"] == "1d"
        assert env["comparability"] == "comparable"
        assert env["as_of"] is not None

    def test_custom_metadata(self):
        env = build_series_envelope(
            [["2026-07-01", 50.0]],
            unit="%/8h",
            provider="Hyperliquid",
            scope="exchange",
            timeframe="8h",
            as_of="2026-07-01T12:00:00Z",
            comparability="limited",
            comparability_notes=["Only covers one exchange"],
        )
        assert env["scope"] == "exchange"
        assert env["timeframe"] == "8h"
        assert env["as_of"] == "2026-07-01T12:00:00Z"
        assert env["comparability"] == "limited"
        assert "Only covers one exchange" in env["comparability_notes"]


# ============================================================
# extract_price_series
# ============================================================

class TestExtractPriceSeries:
    def test_basic_extraction(self):
        records = [
            {"date": "2026-07-01", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000},
            {"date": "2026-07-02", "open": 103, "high": 106, "low": 102, "close": 105, "volume": 1100},
        ]
        result = extract_price_series(records)
        assert result == [["2026-07-01", 103.0], ["2026-07-02", 105.0]]

    def test_empty_records(self):
        assert extract_price_series([]) == []
        assert extract_price_series(None) == []

    def test_missing_close_skipped(self):
        records = [
            {"date": "2026-07-01", "close": 100},
            {"date": "2026-07-02"},  # no close
            {"date": "2026-07-03", "close": 102},
        ]
        result = extract_price_series(records)
        assert len(result) == 2

    def test_nan_close_filtered(self):
        records = [
            {"date": "2026-07-01", "close": 100},
            {"date": "2026-07-02", "close": float("nan")},
            {"date": "2026-07-03", "close": 102},
        ]
        result = extract_price_series(records)
        assert len(result) == 2

    def test_max_days_trim(self):
        from datetime import date, timedelta
        base = date(2026, 1, 1)
        records = [
            {"date": (base + timedelta(days=i)).isoformat(), "close": 100 + i}
            for i in range(100)
        ]
        result = extract_price_series(records, max_days=90)
        assert len(result) == 90


# ============================================================
# inner_join_series
# ============================================================

class TestInnerJoinSeries:
    def test_basic_join(self):
        a = [["2026-07-01", 100], ["2026-07-02", 101], ["2026-07-03", 102]]
        b = [["2026-07-02", 200], ["2026-07-03", 201], ["2026-07-04", 202]]
        ja, jb = inner_join_series(a, b)
        assert len(ja) == 2
        assert len(jb) == 2
        assert ja[0] == ["2026-07-02", 101]
        assert jb[0] == ["2026-07-02", 200]

    def test_no_overlap(self):
        a = [["2026-07-01", 100]]
        b = [["2026-07-05", 200]]
        ja, jb = inner_join_series(a, b)
        assert ja == []
        assert jb == []

    def test_empty_input(self):
        ja, jb = inner_join_series([], [["2026-07-01", 100]])
        assert ja == []
        assert jb == []

    def test_does_not_forward_fill(self):
        """Inner join must NOT forward-fill missing dates."""
        a = [["2026-07-01", 100], ["2026-07-03", 102]]
        b = [["2026-07-01", 200], ["2026-07-02", 201], ["2026-07-03", 202]]
        ja, jb = inner_join_series(a, b)
        # Only dates in BOTH: 07-01 and 07-03 (not 07-02)
        assert len(ja) == 2
        dates_a = [p[0] for p in ja]
        assert "2026-07-02" not in dates_a

    def test_date_misalignment(self):
        """不同起始日期的 series 只 join 共同日期。"""
        a = [["2026-06-28", 95], ["2026-06-29", 96], ["2026-06-30", 97], ["2026-07-01", 100]]
        b = [["2026-07-01", 200], ["2026-07-02", 201]]
        ja, jb = inner_join_series(a, b)
        assert len(ja) == 1
        assert ja[0][0] == "2026-07-01"


# ============================================================
# calc_relative_strength
# ============================================================

class TestCalcRelativeStrength:
    def test_basic_ratio(self):
        a = [["2026-07-01", 100], ["2026-07-02", 110]]
        b = [["2026-07-01", 50], ["2026-07-02", 55]]
        result = calc_relative_strength(a, b)
        assert len(result) == 2
        assert result[0][0] == "2026-07-01"
        assert abs(result[0][1] - 2.0) < 1e-10
        assert abs(result[1][1] - 2.0) < 1e-10

    def test_zero_denominator_skipped(self):
        a = [["2026-07-01", 100], ["2026-07-02", 110], ["2026-07-03", 120]]
        b = [["2026-07-01", 50], ["2026-07-02", 0], ["2026-07-03", 60]]
        result = calc_relative_strength(a, b)
        assert len(result) == 2  # 07-02 skipped
        dates = [p[0] for p in result]
        assert "2026-07-02" not in dates

    def test_empty_series(self):
        assert calc_relative_strength([], []) == []

    def test_no_shared_dates(self):
        a = [["2026-07-01", 100]]
        b = [["2026-07-05", 200]]
        result = calc_relative_strength(a, b)
        assert result == []

    def test_all_zeros_denominator(self):
        a = [["2026-07-01", 100], ["2026-07-02", 110]]
        b = [["2026-07-01", 0], ["2026-07-02", 0]]
        result = calc_relative_strength(a, b)
        assert result == []

    def test_result_values_finite(self):
        """Property: all output ratios must be finite."""
        from datetime import date, timedelta
        import random
        random.seed(123)
        base = date(2026, 4, 1)
        a = [[(base + timedelta(days=i)).isoformat(), random.uniform(50, 150)] for i in range(60)]
        b = [[(base + timedelta(days=i)).isoformat(), random.uniform(0, 100)] for i in range(60)]
        result = calc_relative_strength(a, b)
        for _, val in result:
            assert math.isfinite(val)
