"""
series_utils.py — Shared series processing utilities for HOYA BIT tools.

Provides reusable functions for normalizing, joining, and wrapping
time-series data used across all tool lambdas.

Dependencies: Python stdlib only (math, datetime).
"""

import math
from datetime import datetime, timezone

__all__ = [
    "normalize_series",
    "build_series_envelope",
    "extract_price_series",
    "inner_join_series",
    "calc_relative_strength",
]


def _is_finite(value):
    """Return True if value is a finite float (not None, NaN, or Inf)."""
    if value is None:
        return False
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _normalize_date(date_str):
    """
    Normalize a date string to UTC YYYY-MM-DD format.

    Accepts ISO-8601 variants (with or without time/timezone).
    Returns a YYYY-MM-DD string or None if parsing fails.
    """
    if not isinstance(date_str, str):
        # Handle date/datetime objects
        try:
            return date_str.strftime("%Y-%m-%d")
        except (AttributeError, TypeError):
            return None

    # Strip whitespace
    date_str = date_str.strip()

    # Try common formats
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Convert to UTC if timezone-aware
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Last resort: try taking first 10 chars if they look like YYYY-MM-DD
    if len(date_str) >= 10 and date_str[4] == "-" and date_str[7] == "-":
        candidate = date_str[:10]
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate
        except ValueError:
            pass

    return None


def normalize_series(points, max_days=90):
    """
    Normalize a time-series of [date_str, value] pairs.

    Steps:
      1. Normalize each date to UTC YYYY-MM-DD.
      2. Filter out entries with non-finite values (NaN, Inf, None).
      3. Deduplicate by date, keeping the LAST occurrence.
      4. Sort ascending by date.
      5. Trim to the most recent `max_days` entries.

    Args:
        points: List of [date_str, value] pairs (or any 2-element sequence).
        max_days: Maximum number of data points to retain (default 90).

    Returns:
        List of [date_str, float_value] pairs, cleaned and sorted.
    """
    if not points:
        return []

    cleaned = {}
    for point in points:
        if not point or len(point) < 2:
            continue

        date_str, value = point[0], point[1]

        # Normalize date
        normalized_date = _normalize_date(date_str)
        if normalized_date is None:
            continue

        # Check value is finite
        if not _is_finite(value):
            continue

        # Keep last occurrence for deduplication
        cleaned[normalized_date] = float(value)

    # Sort ascending by date
    sorted_pairs = sorted(cleaned.items(), key=lambda x: x[0])

    # Trim to most recent max_days entries
    if max_days is not None and len(sorted_pairs) > max_days:
        sorted_pairs = sorted_pairs[-max_days:]

    return [[date, val] for date, val in sorted_pairs]


def build_series_envelope(
    points,
    *,
    unit,
    provider,
    pair=None,
    scope=None,
    timeframe="1d",
    as_of=None,
    comparability="comparable",
    comparability_notes=None,
):
    """
    Wrap normalized series points with a metadata envelope.

    Args:
        points: List of [date_str, value] pairs (already normalized).
        unit: Unit of measurement (e.g., 'USD', 'ratio', '%').
        provider: Data provider name (e.g., 'coingecko', 'glassnode').
        pair: Trading pair identifier (e.g., 'BTC/USD'). Optional.
        scope: Scope descriptor (e.g., 'global', 'exchange'). Optional.
        timeframe: Data granularity (default '1d').
        as_of: Timestamp string for data freshness. Defaults to now (UTC).
        comparability: Series comparability tag (default 'comparable').
        comparability_notes: Optional notes on comparability limitations.

    Returns:
        Dict with keys: points, unit, provider, pair, scope, timeframe,
        as_of, comparability, comparability_notes.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "points": points,
        "unit": unit,
        "provider": provider,
        "pair": pair,
        "scope": scope,
        "timeframe": timeframe,
        "as_of": as_of,
        "comparability": comparability,
        "comparability_notes": comparability_notes,
    }


def extract_price_series(price_raw_records, max_days=90):
    """
    Extract and normalize a price series from raw OHLCV records.

    Each record is expected to be a dict with at least 'date' and 'close' keys.

    Args:
        price_raw_records: List of dicts with 'date' and 'close' fields.
        max_days: Maximum entries to retain (default 90).

    Returns:
        Normalized list of [date_str, close_price] pairs.
    """
    if not price_raw_records:
        return []

    raw_points = []
    for record in price_raw_records:
        if not isinstance(record, dict):
            continue
        date_val = record.get("date")
        close_val = record.get("close")
        if date_val is None or close_val is None:
            continue
        raw_points.append([date_val, close_val])

    return normalize_series(raw_points, max_days=max_days)


def inner_join_series(series_a, series_b):
    """
    Inner-join two series on date, retaining only shared dates.

    Does NOT forward-fill missing values. Only dates present in both
    series are included in the output.

    Args:
        series_a: List of [date_str, value] pairs.
        series_b: List of [date_str, value] pairs.

    Returns:
        Tuple (joined_a, joined_b) where each is a list of [date, value]
        pairs containing only the dates present in both inputs, sorted
        ascending by date.
    """
    if not series_a or not series_b:
        return ([], [])

    # Build lookup dicts
    map_a = {point[0]: point[1] for point in series_a}
    map_b = {point[0]: point[1] for point in series_b}

    # Find shared dates
    shared_dates = sorted(set(map_a.keys()) & set(map_b.keys()))

    joined_a = [[d, map_a[d]] for d in shared_dates]
    joined_b = [[d, map_b[d]] for d in shared_dates]

    return (joined_a, joined_b)


def calc_relative_strength(series_a, series_b):
    """
    Compute relative strength (ratio) of series_a to series_b.

    For each shared date, calculates value_a / value_b.
    Skips dates where the denominator is zero.

    Args:
        series_a: List of [date_str, value] pairs.
        series_b: List of [date_str, value] pairs.

    Returns:
        List of [date_str, ratio] pairs for each shared date with
        non-zero denominator, sorted ascending by date.
    """
    joined_a, joined_b = inner_join_series(series_a, series_b)

    result = []
    for point_a, point_b in zip(joined_a, joined_b):
        date = point_a[0]
        val_a = point_a[1]
        val_b = point_b[1]

        # Skip zero denominator
        if val_b == 0 or val_b == 0.0:
            continue

        ratio = val_a / val_b

        # Ensure result is finite
        if math.isfinite(ratio):
            result.append([date, ratio])

    return result
