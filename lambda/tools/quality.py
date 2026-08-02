"""資料工具共用品質與可靠性能力。

本模組不包含任何特定資料來源邏輯，集中提供：
- C1 v1.0 結果標準化
- freshness / comparability / reliability metadata
- anomaly_flags 固定 schema
- timeout、429/5xx 與連線錯誤的有限重試
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import requests

import config

SCHEMA_VERSION = "1.0"
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
COMPARABILITY_STATUSES = {"comparable", "limited", "not_comparable", "unknown"}


class ToolHttpError(RuntimeError):
    """HTTP 重試耗盡或不可重試錯誤，附帶結構化嘗試資訊。"""

    def __init__(self, message: str, request_metadata: dict[str, Any]):
        super().__init__(message)
        self.request_metadata = request_metadata


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evaluate_freshness(
    as_of: Any,
    max_age_seconds: int | float | None,
    reference_time: Any = None,
) -> dict[str, Any]:
    """以資料時間和參考時間決定 fresh / stale / unknown。"""
    as_of_dt = _parse_datetime(as_of)
    reference_dt = _parse_datetime(reference_time) or datetime.now(timezone.utc)
    max_age = int(max_age_seconds) if max_age_seconds is not None else None

    if as_of_dt is None or max_age is None or max_age < 0:
        return {
            "status": "unknown",
            "age_seconds": None,
            "max_age_seconds": max_age,
            "reference_time": reference_dt.isoformat(),
        }

    age_seconds = max(0, int((reference_dt - as_of_dt).total_seconds()))
    return {
        "status": "fresh" if age_seconds <= max_age else "stale",
        "age_seconds": age_seconds,
        "max_age_seconds": max_age,
        "reference_time": reference_dt.isoformat(),
    }


def build_quality_metadata(
    *,
    as_of: Any,
    max_age_seconds: int | float | None,
    reference_time: Any = None,
    attempts: int = 1,
    max_attempts: int | None = None,
    fallback_used: bool = False,
    primary_provider: str | None = None,
    rate_limited: bool = False,
    partial: bool = False,
    errors: list[str] | None = None,
    comparability_status: str = "comparable",
    comparability_notes: list[str] | None = None,
) -> dict[str, Any]:
    """建立 C1 quality 區塊。"""
    if comparability_status not in COMPARABILITY_STATUSES:
        comparability_status = "unknown"
    notes = [str(note) for note in (comparability_notes or []) if str(note).strip()]
    return {
        "freshness": evaluate_freshness(as_of, max_age_seconds, reference_time),
        "reliability": {
            "attempts": max(0, int(attempts)),
            "max_attempts": int(max_attempts or config.TOOL_HTTP_MAX_ATTEMPTS),
            "fallback_used": bool(fallback_used),
            "primary_provider": primary_provider,
            "rate_limited": bool(rate_limited),
            "partial": bool(partial),
            "errors": [str(error) for error in (errors or []) if str(error).strip()],
        },
        "comparability": {
            "status": comparability_status,
            "notes": notes,
        },
    }


def standardize_tool_result(
    result: dict[str, Any] | None,
    *,
    provider: str,
    endpoint: Any,
    symbol: str | None,
    pair: str | None,
    timeframe: str,
    window: Any,
    unit: Any,
    as_of: Any = None,
    fetched_at: Any = None,
    max_age_seconds: int | float | None = None,
    reference_time: Any = None,
    attempts: int = 1,
    max_attempts: int | None = None,
    fallback_used: bool = False,
    primary_provider: str | None = None,
    rate_limited: bool = False,
    partial: bool = False,
    errors: list[str] | None = None,
    comparability_status: str = "comparable",
    comparability_notes: list[str] | None = None,
) -> dict[str, Any]:
    """把舊式工具 dict 擴充成 C1 v1.0，保留既有欄位。"""
    normalized = dict(result or {})
    content_reference = dict(normalized.get("content_reference") or {})
    fetched_value = fetched_at or content_reference.get("fetched_at") or utc_now_iso()
    as_of_value = as_of if as_of is not None else content_reference.get("as_of")
    notes = list(comparability_notes or content_reference.get("comparability_notes") or [])

    quality = build_quality_metadata(
        as_of=as_of_value,
        max_age_seconds=max_age_seconds,
        reference_time=reference_time or fetched_value,
        attempts=attempts,
        max_attempts=max_attempts,
        fallback_used=fallback_used,
        primary_provider=primary_provider or provider,
        rate_limited=rate_limited,
        partial=partial,
        errors=errors,
        comparability_status=comparability_status,
        comparability_notes=notes,
    )

    required_metadata = {
        "as_of": as_of_value,
        "fetched_at": str(fetched_value),
        "timeframe": timeframe,
        "window": window,
        "unit": unit,
        "symbol": str(symbol).upper() if symbol else "MARKET",
        "pair": pair,
        "provider": provider,
        "endpoint": endpoint,
        "freshness_status": quality["freshness"]["status"],
        "comparability_notes": notes,
        "quality": quality,
    }
    for key, value in required_metadata.items():
        content_reference[key] = value

    is_error = bool(normalized.get("error"))
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["status"] = "error" if is_error else ("partial" if partial else "success")
    normalized["source"] = normalized.get("source") or endpoint or provider
    normalized["content_reference"] = content_reference
    normalized["anomaly_flags"] = list(normalized.get("anomaly_flags") or [])

    if not is_error:
        normalized.setdefault("raw", {})
        normalized.setdefault("summary", "No summary available")
    return normalized


def make_anomaly_flag(
    *,
    signal_id: str,
    name: str,
    severity: str,
    direction: str,
    value: Any,
    unit: str,
    threshold: str,
    window: str,
    as_of: Any,
    message: str,
    percentile: Any = None,
) -> dict[str, Any]:
    """建立固定 schema 的單源異常旗標。"""
    return {
        "signal_id": signal_id,
        "name": name,
        "severity": severity,
        "direction": direction,
        "value": value,
        "unit": unit,
        "percentile": percentile,
        "threshold": threshold,
        "window": window,
        "as_of": as_of,
        "message": message,
    }


def _retry_delay(response: Any, attempt: int, backoff_seconds: float) -> float:
    retry_after = None
    if response is not None:
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(float(retry_after), config.TOOL_RETRY_AFTER_MAX_SECONDS)
        except (TypeError, ValueError):
            pass
    return min(backoff_seconds * (2 ** max(0, attempt - 1)), config.TOOL_RETRY_AFTER_MAX_SECONDS)


def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: int | float | None = None,
    max_attempts: int | None = None,
    backoff_seconds: float | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> tuple[Any, dict[str, Any]]:
    """執行有限 HTTP 重試並回傳 response 與嘗試 metadata。

    只有 timeout、connection error、429 與暫時性 5xx 會重試；其他 HTTP
    錯誤與資料解析錯誤交由呼叫端處理。
    """
    method_upper = method.upper().strip()
    request_func = getattr(requests, method_upper.lower(), None)
    if request_func is None:
        raise ValueError(f"Unsupported HTTP method: {method}")

    timeout_value = timeout if timeout is not None else config.TOOL_HTTP_TIMEOUT_SECONDS
    attempts_limit = max(1, int(max_attempts or config.TOOL_HTTP_MAX_ATTEMPTS))
    backoff = float(
        config.TOOL_HTTP_BACKOFF_SECONDS if backoff_seconds is None else backoff_seconds
    )
    rate_limited = False
    attempt_errors: list[str] = []

    for attempt in range(1, attempts_limit + 1):
        response = None
        try:
            response = request_func(url, timeout=timeout_value, **kwargs)
            status_code = getattr(response, "status_code", None)
            if status_code in TRANSIENT_HTTP_STATUSES:
                rate_limited = rate_limited or status_code == 429
                message = f"HTTP {status_code} from {url}"
                attempt_errors.append(message)
                if attempt < attempts_limit:
                    sleep_func(_retry_delay(response, attempt, backoff))
                    continue
                raise ToolHttpError(
                    message,
                    {
                        "attempts": attempt,
                        "max_attempts": attempts_limit,
                        "rate_limited": rate_limited,
                        "errors": attempt_errors,
                        "endpoint": url,
                    },
                )

            response.raise_for_status()
            return response, {
                "attempts": attempt,
                "max_attempts": attempts_limit,
                "rate_limited": rate_limited,
                "errors": attempt_errors,
                "endpoint": url,
            }
        except ToolHttpError:
            raise
        except (requests.Timeout, requests.ConnectionError) as exc:
            attempt_errors.append(f"{type(exc).__name__}: {exc}")
            if attempt < attempts_limit:
                sleep_func(_retry_delay(response, attempt, backoff))
                continue
            raise ToolHttpError(
                f"{type(exc).__name__} after {attempt} attempts: {exc}",
                {
                    "attempts": attempt,
                    "max_attempts": attempts_limit,
                    "rate_limited": rate_limited,
                    "errors": attempt_errors,
                    "endpoint": url,
                },
            ) from exc
        except requests.RequestException as exc:
            raise ToolHttpError(
                f"{type(exc).__name__}: {exc}",
                {
                    "attempts": attempt,
                    "max_attempts": attempts_limit,
                    "rate_limited": rate_limited,
                    "errors": attempt_errors + [f"{type(exc).__name__}: {exc}"],
                    "endpoint": url,
                },
            ) from exc

    raise ToolHttpError(
        f"Request failed without response: {url}",
        {
            "attempts": attempts_limit,
            "max_attempts": attempts_limit,
            "rate_limited": rate_limited,
            "errors": attempt_errors,
            "endpoint": url,
        },
    )



class RetryingRequestsFacade:
    """保留 requests.get/post 呼叫介面，內部套用 request_with_retry。

    既有測試可繼續 patch `tools.<module>.requests.get/post`；未 patch 的實際
    呼叫則會使用共用 timeout、429/5xx 與連線錯誤重試政策。
    """

    def get(self, url: str, **kwargs: Any) -> Any:
        response, _ = request_with_retry("GET", url, **kwargs)
        return response

    def post(self, url: str, **kwargs: Any) -> Any:
        response, _ = request_with_retry("POST", url, **kwargs)
        return response
