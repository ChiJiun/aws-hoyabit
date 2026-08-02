"""
report_schema.py — C7 結構化報告 schema 定義、驗證與建構

無網路副作用、不讀環境變數、不 import report/handler/frontend。
schema_version = 1.0
"""

import math
import re
from datetime import datetime, timedelta

# ─── Constants & Enums ───────────────────────────────────────────────────────

C7_SCHEMA_VERSION = "1.0"

QUESTION_TYPES = {"single_integration", "hypothesis", "comparison"}
STANCE_VALUES = {"bullish", "bearish", "neutral", "mixed"}
DIMENSION_STATES = {"strong", "weak", "neutral", "na"}
SIGNAL_LEVELS = {"red", "yellow"}

CONFIDENCE_LABELS = {
    (0.0, 0.3): "低",
    (0.3, 0.6): "中等",
    (0.6, 0.8): "中高",
    (0.8, 1.01): "高",
}

C7_REQUIRED_FIELDS = (
    "schema_version",
    "question_type",
    "symbols",
    "verdict",
    "dimensions",
    "signals",
    "checked_normal",
    "series",
    "coverage",
    "watchlist",
)

VERDICT_REQUIRED = ("text", "stance", "confidence", "confidence_label", "invalidation")
DIMENSION_REQUIRED = ("name", "state", "headline", "evidence_ids")
SIGNAL_REQUIRED = ("level", "title", "detail", "evidence_ids")
COVERAGE_REQUIRED = ("pct", "got", "missing")

MAX_SERIES_DAYS = 90


# ─── Validation Helpers ──────────────────────────────────────────────────────

def _err(path, code, message):
    """Build a single validation error dict."""
    return {"path": path, "code": code, "message": message}


def _is_finite(value):
    """Check if a numeric value is finite (not NaN/Inf)."""
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _parse_date(s):
    """Parse ISO date string (YYYY-MM-DD). Returns datetime.date or None."""
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _confidence_label(confidence):
    """Derive confidence label from numeric value."""
    for (lo, hi), label in CONFIDENCE_LABELS.items():
        if lo <= confidence < hi:
            return label
    return "高"



# ─── C7 Validator ────────────────────────────────────────────────────────────

def validate_report_data(value, evidence_ids=None):
    """Validate a C7 report_data dict.

    Args:
        value: The report_data dict to validate.
        evidence_ids: Optional set/list of known evidence IDs for FK check.

    Returns:
        list[dict]: Each dict has {path, code, message}. Empty list = valid.
        Never raises on normal input errors; never mutates input.
    """
    errors = []

    if not isinstance(value, dict):
        return [_err("$", "type", "report_data must be a dict")]

    # Required top-level fields
    for field in C7_REQUIRED_FIELDS:
        if field not in value:
            errors.append(_err(f"$.{field}", "required", f"missing required field '{field}'"))

    if errors:
        # If required fields are missing, remaining checks are unreliable
        return errors

    # schema_version
    if value.get("schema_version") != C7_SCHEMA_VERSION:
        errors.append(_err("$.schema_version", "value", f"must be '{C7_SCHEMA_VERSION}'"))

    # question_type
    qt = value.get("question_type")
    if qt not in QUESTION_TYPES:
        errors.append(_err("$.question_type", "enum", f"must be one of {sorted(QUESTION_TYPES)}"))

    # symbols
    symbols = value.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        errors.append(_err("$.symbols", "type", "symbols must be a non-empty list"))
    else:
        if qt == "comparison" and len(symbols) != 2:
            errors.append(_err("$.symbols", "length", "comparison requires exactly 2 symbols"))
        elif qt in ("single_integration", "hypothesis") and len(symbols) != 1:
            errors.append(_err("$.symbols", "length", f"{qt} requires exactly 1 symbol"))

    # verdict
    verdict = value.get("verdict")
    if not isinstance(verdict, dict):
        errors.append(_err("$.verdict", "type", "verdict must be a dict"))
    else:
        for f in VERDICT_REQUIRED:
            if f not in verdict:
                errors.append(_err(f"$.verdict.{f}", "required", f"missing '{f}'"))
        if "stance" in verdict and verdict["stance"] not in STANCE_VALUES:
            errors.append(_err("$.verdict.stance", "enum", f"must be one of {sorted(STANCE_VALUES)}"))
        conf = verdict.get("confidence")
        if conf is not None:
            if not _is_finite(conf) or conf < 0 or conf > 1:
                errors.append(_err("$.verdict.confidence", "range", "must be finite 0–1"))

    # dimensions
    dims = value.get("dimensions")
    if not isinstance(dims, list):
        errors.append(_err("$.dimensions", "type", "dimensions must be a list"))
    else:
        for i, dim in enumerate(dims):
            path = f"$.dimensions[{i}]"
            if not isinstance(dim, dict):
                errors.append(_err(path, "type", "each dimension must be a dict"))
                continue
            for f in DIMENSION_REQUIRED:
                if f not in dim:
                    errors.append(_err(f"{path}.{f}", "required", f"missing '{f}'"))
            if "state" in dim and dim["state"] not in DIMENSION_STATES:
                errors.append(_err(f"{path}.state", "enum", f"must be one of {sorted(DIMENSION_STATES)}"))
            _validate_evidence_ids_field(dim, path, evidence_ids, errors)

    # signals
    signals = value.get("signals")
    if not isinstance(signals, list):
        errors.append(_err("$.signals", "type", "signals must be a list"))
    else:
        for i, sig in enumerate(signals):
            path = f"$.signals[{i}]"
            if not isinstance(sig, dict):
                errors.append(_err(path, "type", "each signal must be a dict"))
                continue
            for f in SIGNAL_REQUIRED:
                if f not in sig:
                    errors.append(_err(f"{path}.{f}", "required", f"missing '{f}'"))
            if "level" in sig and sig["level"] not in SIGNAL_LEVELS:
                errors.append(_err(f"{path}.level", "enum", f"must be one of {sorted(SIGNAL_LEVELS)}"))
            _validate_evidence_ids_field(sig, path, evidence_ids, errors)
            # metrics finite check
            for j, m in enumerate(sig.get("metrics", []) or []):
                if isinstance(m, dict):
                    v = m.get("value")
                    if v is not None and not _is_finite(v):
                        errors.append(_err(f"{path}.metrics[{j}].value", "finite", "must be finite"))
                    p = m.get("percentile")
                    if p is not None and not _is_finite(p):
                        errors.append(_err(f"{path}.metrics[{j}].percentile", "finite", "must be finite"))

    # checked_normal
    cn = value.get("checked_normal")
    if not isinstance(cn, list):
        errors.append(_err("$.checked_normal", "type", "must be a list"))

    # hypothesis / comparison conditional
    if qt == "hypothesis":
        hyp = value.get("hypothesis")
        if not isinstance(hyp, dict):
            errors.append(_err("$.hypothesis", "required", "hypothesis object required for hypothesis type"))
        else:
            for f in ("statement", "supporting", "opposing", "verdict_reason"):
                if f not in hyp:
                    errors.append(_err(f"$.hypothesis.{f}", "required", f"missing '{f}'"))
        if value.get("comparison") is not None:
            errors.append(_err("$.comparison", "null_expected", "comparison must be null for hypothesis type"))
    elif qt == "comparison":
        comp = value.get("comparison")
        if not isinstance(comp, dict):
            errors.append(_err("$.comparison", "required", "comparison object required for comparison type"))
        else:
            for f in ("rows", "when_prefer_a", "when_prefer_b"):
                if f not in comp:
                    errors.append(_err(f"$.comparison.{f}", "required", f"missing '{f}'"))
        if value.get("hypothesis") is not None:
            errors.append(_err("$.hypothesis", "null_expected", "hypothesis must be null for comparison type"))
    else:
        # single_integration
        if value.get("hypothesis") is not None:
            errors.append(_err("$.hypothesis", "null_expected", "hypothesis must be null for single_integration"))
        if value.get("comparison") is not None:
            errors.append(_err("$.comparison", "null_expected", "comparison must be null for single_integration"))

    # series
    errors.extend(_validate_series(value.get("series")))

    # coverage
    errors.extend(_validate_coverage(value.get("coverage")))

    # watchlist
    wl = value.get("watchlist")
    if not isinstance(wl, list):
        errors.append(_err("$.watchlist", "type", "watchlist must be a list"))

    return errors


def _validate_evidence_ids_field(obj, path, known_ids, errors):
    """Check evidence_ids FK constraint within a dimension or signal."""
    eids = obj.get("evidence_ids")
    if not isinstance(eids, list):
        return
    if known_ids is not None:
        known = set(known_ids) if not isinstance(known_ids, set) else known_ids
        for eid in eids:
            if eid not in known:
                errors.append(_err(f"{path}.evidence_ids", "fk", f"evidence_id '{eid}' not found"))


def _validate_series(series):
    """Validate series: dates ascending, finite values, max 90 days."""
    errors = []
    if not isinstance(series, dict):
        errors.append(_err("$.series", "type", "series must be a dict"))
        return errors
    for key, symbol_data in series.items():
        if not isinstance(symbol_data, dict):
            continue
        for symbol, points in symbol_data.items():
            path = f"$.series.{key}.{symbol}"
            if not isinstance(points, list):
                errors.append(_err(path, "type", "series points must be a list"))
                continue
            prev_date = None
            for i, point in enumerate(points):
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    errors.append(_err(f"{path}[{i}]", "format", "each point must be [date, value]"))
                    continue
                date_str, val = point[0], point[1]
                d = _parse_date(date_str)
                if d is None:
                    errors.append(_err(f"{path}[{i}]", "date", f"invalid date '{date_str}'"))
                    continue
                if not _is_finite(val):
                    errors.append(_err(f"{path}[{i}]", "finite", f"value must be finite, got {val}"))
                if prev_date is not None and d <= prev_date:
                    errors.append(_err(f"{path}[{i}]", "order", "dates must be strictly ascending"))
                prev_date = d
            # 90-day span check
            if len(points) >= 2:
                first_d = _parse_date(points[0][0]) if isinstance(points[0], (list, tuple)) and len(points[0]) >= 2 else None
                last_d = _parse_date(points[-1][0]) if isinstance(points[-1], (list, tuple)) and len(points[-1]) >= 2 else None
                if first_d and last_d and (last_d - first_d).days > MAX_SERIES_DAYS:
                    errors.append(_err(path, "span", f"series span exceeds {MAX_SERIES_DAYS} days"))
    return errors


def _validate_coverage(coverage):
    """Validate coverage object."""
    errors = []
    if not isinstance(coverage, dict):
        errors.append(_err("$.coverage", "type", "coverage must be a dict"))
        return errors
    for f in COVERAGE_REQUIRED:
        if f not in coverage:
            errors.append(_err(f"$.coverage.{f}", "required", f"missing '{f}'"))
    pct = coverage.get("pct")
    if pct is not None:
        if not isinstance(pct, (int, float)):
            errors.append(_err("$.coverage.pct", "type", "pct must be null or numeric 0–100"))
        elif not _is_finite(pct) or pct < 0 or pct > 100:
            errors.append(_err("$.coverage.pct", "range", "pct must be null or 0–100"))
    got = coverage.get("got")
    if got is not None and not isinstance(got, list):
        errors.append(_err("$.coverage.got", "type", "got must be a list"))
    missing = coverage.get("missing")
    if missing is not None and not isinstance(missing, list):
        errors.append(_err("$.coverage.missing", "type", "missing must be a list"))
    return errors



# ─── ReportModel ─────────────────────────────────────────────────────────────

class ReportModel:
    """Single intermediate model from which both Markdown and C7 are derived.

    Attributes mirror C7 schema fields. Created by build_report_model(),
    consumed by render_report_model_md() and build_report_data().
    """

    __slots__ = (
        "question_type", "symbols", "verdict_text", "stance", "confidence",
        "confidence_label", "invalidation", "dimensions", "signals",
        "checked_normal", "hypothesis", "comparison", "series", "coverage",
        "watchlist",
    )

    def __init__(
        self,
        question_type,
        symbols,
        verdict_text="",
        stance="neutral",
        confidence=0.5,
        confidence_label=None,
        invalidation="",
        dimensions=None,
        signals=None,
        checked_normal=None,
        hypothesis=None,
        comparison=None,
        series=None,
        coverage=None,
        watchlist=None,
    ):
        self.question_type = question_type
        self.symbols = list(symbols) if symbols else []
        self.verdict_text = verdict_text or ""
        self.stance = stance if stance in STANCE_VALUES else "neutral"
        self.confidence = float(confidence) if _is_finite(confidence) else 0.5
        self.confidence_label = confidence_label or _confidence_label(self.confidence)
        self.invalidation = invalidation or ""
        self.dimensions = dimensions or []
        self.signals = signals or []
        self.checked_normal = checked_normal or []
        self.hypothesis = hypothesis
        self.comparison = comparison
        self.series = series or {}
        self.coverage = coverage or {"pct": None, "got": [], "missing": []}
        self.watchlist = watchlist or []

    def to_report_data(self):
        """Convert to C7 report_data dict."""
        return {
            "schema_version": C7_SCHEMA_VERSION,
            "question_type": self.question_type,
            "symbols": self.symbols,
            "verdict": {
                "text": self.verdict_text,
                "stance": self.stance,
                "confidence": self.confidence,
                "confidence_label": self.confidence_label,
                "invalidation": self.invalidation,
            },
            "dimensions": self.dimensions,
            "signals": self.signals,
            "checked_normal": self.checked_normal,
            "hypothesis": self.hypothesis,
            "comparison": self.comparison,
            "series": self.series,
            "coverage": self.coverage,
            "watchlist": self.watchlist,
        }



# ─── build_report_data ───────────────────────────────────────────────────────

def build_report_data(question_type, symbols, analysis_text, evidence_list,
                      execution_log=None, series=None):
    """Build C7 report_data from analysis outputs.

    Fails gracefully: returns None on any error (logs to execution_log if mutable list).
    Never raises, never has network side effects.

    Args:
        question_type: "single_integration" | "hypothesis" | "comparison"
        symbols: List of symbol strings (e.g. ["BTC"] or ["BTC", "ETH"])
        analysis_text: The LLM-generated analysis text
        evidence_list: List of C2 Evidence Records
        execution_log: Optional mutable list; errors appended as log entries
        series: Optional dict of time-series data for charts

    Returns:
        dict (valid C7 report_data) or None on failure.
    """
    try:
        if question_type not in QUESTION_TYPES:
            _log_error(execution_log, f"Invalid question_type: {question_type}")
            return None

        symbols = list(symbols) if symbols else []
        evidence_list = evidence_list if isinstance(evidence_list, list) else []
        analysis_text = str(analysis_text or "")

        # Build evidence ID set for FK validation
        known_ids = set()
        for rec in evidence_list:
            if isinstance(rec, dict) and rec.get("evidence_id"):
                known_ids.add(rec["evidence_id"])

        # Parse structured sections from analysis_text
        verdict = _extract_verdict(analysis_text)
        dimensions = _extract_dimensions(analysis_text, question_type, symbols)
        signals = _extract_signals(analysis_text)
        checked_normal = _extract_checked_normal(analysis_text)
        hypothesis_block = _extract_hypothesis(analysis_text) if question_type == "hypothesis" else None
        comparison_block = _extract_comparison(analysis_text, symbols) if question_type == "comparison" else None
        watchlist = _extract_watchlist(analysis_text)
        coverage = _build_coverage(analysis_text, execution_log)
        normalized_series = _normalize_series(series)

        model = ReportModel(
            question_type=question_type,
            symbols=symbols,
            verdict_text=verdict.get("text", ""),
            stance=verdict.get("stance", "neutral"),
            confidence=verdict.get("confidence", 0.5),
            confidence_label=verdict.get("confidence_label"),
            invalidation=verdict.get("invalidation", ""),
            dimensions=dimensions,
            signals=signals,
            checked_normal=checked_normal,
            hypothesis=hypothesis_block,
            comparison=comparison_block,
            series=normalized_series,
            coverage=coverage,
            watchlist=watchlist,
        )

        report_data = model.to_report_data()

        # Validate before returning
        validation_errors = validate_report_data(report_data, evidence_ids=known_ids)
        if validation_errors:
            error_summary = "; ".join(e["message"] for e in validation_errors[:5])
            _log_error(execution_log, f"C7 validation failed: {error_summary}")
            return None

        return report_data

    except Exception as exc:
        _log_error(execution_log, f"build_report_data exception: {exc}")
        return None


def _log_error(execution_log, message):
    """Append error entry to execution_log if it's a mutable list."""
    if isinstance(execution_log, list):
        execution_log.append({
            "tool_name": "build_report_data",
            "status": "error",
            "note": str(message),
        })


# ─── Extraction Helpers (parse structured sections from analysis_text) ───────

def _extract_verdict(text):
    """Extract verdict block from analysis text.

    Looks for structured markers like [VERDICT], stance:, confidence: patterns.
    """
    verdict = {"text": "", "stance": "neutral", "confidence": 0.5,
               "confidence_label": None, "invalidation": ""}

    # Try structured format: [VERDICT] ... [/VERDICT] or JSON-like
    verdict_match = re.search(
        r"\[VERDICT\](.*?)\[/VERDICT\]", text, re.DOTALL | re.IGNORECASE
    )
    if verdict_match:
        block = verdict_match.group(1).strip()
        verdict["text"] = _extract_field(block, "text") or block.split("\n")[0]
    else:
        # Fallback: first substantial line from 市場判斷 section
        judgment_match = re.search(r"(?:^|\n)\s*#*\s*市場判斷\s*\n(.*?)(?=\n\s*#|\Z)", text, re.DOTALL)
        if judgment_match:
            lines = [l.strip() for l in judgment_match.group(1).strip().split("\n") if l.strip()]
            verdict["text"] = lines[0] if lines else ""

    # Stance
    stance_match = re.search(r"stance\s*[:=]\s*(\w+)", text, re.IGNORECASE)
    if stance_match and stance_match.group(1).lower() in STANCE_VALUES:
        verdict["stance"] = stance_match.group(1).lower()

    # Confidence
    conf_match = re.search(r"confidence\s*[:=]\s*([\d.]+)", text, re.IGNORECASE)
    if conf_match:
        try:
            c = float(conf_match.group(1))
            if 0 <= c <= 1:
                verdict["confidence"] = c
        except ValueError:
            pass

    verdict["confidence_label"] = _confidence_label(verdict["confidence"])

    # Invalidation
    inv_match = re.search(r"invalidation\s*[:=]\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if inv_match:
        verdict["invalidation"] = inv_match.group(1).strip()

    return verdict


def _extract_field(block, field_name):
    """Extract a named field from a text block."""
    match = re.search(rf"{field_name}\s*[:=]\s*(.+?)(?:\n|$)", block, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_dimensions(text, question_type, symbols):
    """Extract dimension assessments from analysis text."""
    dimensions = []

    # Look for structured dimension markers
    dim_pattern = re.compile(
        r"\[DIM(?:ENSION)?\]\s*name\s*[:=]\s*(.+?)\n"
        r".*?state\s*[:=]\s*(\w+).*?\n"
        r".*?headline\s*[:=]\s*(.+?)\n"
        r".*?evidence_ids\s*[:=]\s*\[([^\]]*)\]",
        re.DOTALL | re.IGNORECASE,
    )

    for match in dim_pattern.finditer(text):
        name = match.group(1).strip()
        state = match.group(2).strip().lower()
        headline = match.group(3).strip()
        ids_raw = match.group(4).strip()
        eids = [e.strip().strip('"\'') for e in ids_raw.split(",") if e.strip()]

        if state not in DIMENSION_STATES:
            state = "neutral"

        dim = {
            "name": name,
            "state": state,
            "headline": headline,
            "evidence_ids": eids,
        }

        # For comparison, add per_symbol if available
        if question_type == "comparison" and len(symbols) == 2:
            dim["per_symbol"] = {s: {} for s in symbols}

        dimensions.append(dim)

    return dimensions


def _extract_signals(text):
    """Extract warning signals from analysis text."""
    signals = []
    sig_pattern = re.compile(
        r"\[SIGNAL\]\s*level\s*[:=]\s*(\w+).*?\n"
        r".*?title\s*[:=]\s*(.+?)\n"
        r".*?detail\s*[:=]\s*(.+?)\n"
        r".*?evidence_ids\s*[:=]\s*\[([^\]]*)\]",
        re.DOTALL | re.IGNORECASE,
    )

    for match in sig_pattern.finditer(text):
        level = match.group(1).strip().lower()
        if level not in SIGNAL_LEVELS:
            level = "yellow"
        title = match.group(2).strip()
        detail = match.group(3).strip()
        ids_raw = match.group(4).strip()
        eids = [e.strip().strip('"\'') for e in ids_raw.split(",") if e.strip()]

        signals.append({
            "level": level,
            "title": title,
            "detail": detail,
            "evidence_ids": eids,
            "metrics": [],
            "caveat": "",
        })

    return signals


def _extract_checked_normal(text):
    """Extract items that were checked and found normal."""
    items = []
    cn_match = re.search(
        r"\[CHECKED_NORMAL\](.*?)\[/CHECKED_NORMAL\]", text, re.DOTALL | re.IGNORECASE
    )
    if cn_match:
        for line in cn_match.group(1).strip().split("\n"):
            line = line.strip().lstrip("-").strip()
            if line:
                items.append(line)
    return items


def _extract_hypothesis(text):
    """Extract hypothesis block for hypothesis question type."""
    hyp = {"statement": "", "supporting": [], "opposing": [], "verdict_reason": ""}

    hyp_match = re.search(
        r"\[HYPOTHESIS\](.*?)\[/HYPOTHESIS\]", text, re.DOTALL | re.IGNORECASE
    )
    if hyp_match:
        block = hyp_match.group(1).strip()
        hyp["statement"] = _extract_field(block, "statement") or ""
        hyp["verdict_reason"] = _extract_field(block, "verdict_reason") or ""

        sup_match = re.search(r"supporting\s*[:=]\s*\[([^\]]*)\]", block, re.IGNORECASE)
        if sup_match:
            hyp["supporting"] = [s.strip().strip('"\'') for s in sup_match.group(1).split(",") if s.strip()]

        opp_match = re.search(r"opposing\s*[:=]\s*\[([^\]]*)\]", block, re.IGNORECASE)
        if opp_match:
            hyp["opposing"] = [s.strip().strip('"\'') for s in opp_match.group(1).split(",") if s.strip()]

    return hyp if hyp["statement"] else hyp


def _extract_comparison(text, symbols):
    """Extract comparison block for comparison question type."""
    comp = {"rows": [], "when_prefer_a": "", "when_prefer_b": ""}

    comp_match = re.search(
        r"\[COMPARISON\](.*?)\[/COMPARISON\]", text, re.DOTALL | re.IGNORECASE
    )
    if comp_match:
        block = comp_match.group(1).strip()
        comp["when_prefer_a"] = _extract_field(block, "when_prefer_a") or ""
        comp["when_prefer_b"] = _extract_field(block, "when_prefer_b") or ""

        row_pattern = re.compile(
            r"\[ROW\]\s*dimension\s*[:=]\s*(.+?)\n.*?edge\s*[:=]\s*(\w+)",
            re.DOTALL | re.IGNORECASE,
        )
        for row_match in row_pattern.finditer(block):
            dim_name = row_match.group(1).strip()
            edge = row_match.group(2).strip()
            row = {"dimension": dim_name, "edge": edge}
            if len(symbols) >= 2:
                row["a"] = {}
                row["b"] = {}
            comp["rows"].append(row)

    return comp


def _extract_watchlist(text):
    """Extract watchlist events."""
    items = []
    wl_match = re.search(
        r"\[WATCHLIST\](.*?)\[/WATCHLIST\]", text, re.DOTALL | re.IGNORECASE
    )
    if wl_match:
        event_pattern = re.compile(
            r"event\s*[:=]\s*(.+?)\n.*?date\s*[:=]\s*(.+?)\n.*?why\s*[:=]\s*(.+?)(?:\n|$)",
            re.DOTALL | re.IGNORECASE,
        )
        for m in event_pattern.finditer(wl_match.group(1)):
            items.append({
                "event": m.group(1).strip(),
                "date": m.group(2).strip(),
                "why": m.group(3).strip(),
            })
    return items


def _build_coverage(text, execution_log):
    """Build coverage from structured markers or execution log."""
    coverage = {"pct": None, "got": [], "missing": []}

    cov_match = re.search(
        r"\[COVERAGE\](.*?)\[/COVERAGE\]", text, re.DOTALL | re.IGNORECASE
    )
    if cov_match:
        block = cov_match.group(1).strip()
        pct_match = re.search(r"pct\s*[:=]\s*([\d.]+|null)", block, re.IGNORECASE)
        if pct_match:
            pct_str = pct_match.group(1)
            if pct_str.lower() == "null":
                coverage["pct"] = None
            else:
                try:
                    coverage["pct"] = float(pct_str)
                except ValueError:
                    pass

        got_match = re.search(r"got\s*[:=]\s*\[([^\]]*)\]", block, re.IGNORECASE)
        if got_match:
            coverage["got"] = [g.strip().strip('"\'') for g in got_match.group(1).split(",") if g.strip()]

        missing_match = re.search(r"missing\s*[:=]\s*\[([^\]]*)\]", block, re.IGNORECASE)
        if missing_match:
            raw = missing_match.group(1).strip()
            if raw:
                # Each missing item should have capability and reason
                for item in raw.split(","):
                    item = item.strip().strip('"\'')
                    if item:
                        coverage["missing"].append({"capability": item, "reason": "unavailable"})

    # Compute pct from got/missing if not explicitly set
    if coverage["pct"] is None and (coverage["got"] or coverage["missing"]):
        total = len(coverage["got"]) + len(coverage["missing"])
        if total > 0:
            coverage["pct"] = round(len(coverage["got"]) / total * 100, 1)

    return coverage


def _normalize_series(series):
    """Normalize series: sort by date ascending, deduplicate, trim to 90 days, check finite."""
    if not isinstance(series, dict):
        return {}

    result = {}
    for metric_key, symbol_data in series.items():
        if not isinstance(symbol_data, dict):
            continue
        result[metric_key] = {}
        for symbol, points in symbol_data.items():
            if not isinstance(points, list):
                continue
            # Filter valid points
            valid = []
            seen_dates = set()
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                date_str = str(point[0])
                val = point[1]
                if not isinstance(val, (int, float)) or not math.isfinite(val):
                    continue
                if _parse_date(date_str) is None:
                    continue
                if date_str in seen_dates:
                    continue
                seen_dates.add(date_str)
                valid.append([date_str, val])

            # Sort ascending
            valid.sort(key=lambda p: p[0])

            # Trim to 90 days from last date
            if valid:
                last_date = _parse_date(valid[-1][0])
                if last_date:
                    cutoff = last_date - timedelta(days=MAX_SERIES_DAYS)
                    valid = [p for p in valid if _parse_date(p[0]) >= cutoff]

            if valid:
                result[metric_key][symbol] = valid

    return result
