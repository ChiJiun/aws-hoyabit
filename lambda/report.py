"""
report.py — 報告渲染

以純本地、決定性的方式整理實際引用證據、分析維度與失敗嘗試。
報告不使用固定類別分母、覆蓋率或維度分數。
C7 report_data 由 report_schema.build_report_data() 產生。
"""

import json
import re
from urllib.parse import urlparse

from report_schema import build_report_data as _c7_build_report_data
from report_schema import validate_report_data as _c7_validate


ANALYSIS_DIMENSIONS = (
    "價格",
    "技術指標",
    "市場結構與流動性",
    "衍生品",
    "鏈上",
    "情緒",
    "預測市場",
    "新聞與公告",
    "總體經濟",
    "DeFi",
    "開發活躍度",
    "機構資料",
    "監管資料",
)

TOOL_DIMENSIONS = {
    "get_price_ohlcv": "價格",
    "compute_quant": "技術指標",
    "get_orderbook_depth": "市場結構與流動性",
    "get_market_dominance": "市場結構與流動性",
    "get_derivatives": "衍生品",
    "get_onchain": "鏈上",
    "get_sentiment": "情緒",
    "get_prediction_market": "預測市場",
    "search_news": "新聞與公告",
    "get_macro": "總體經濟",
    "get_defi_data": "DeFi",
    "get_dev_activity": "開發活躍度",
    "get_coin_metrics": "機構資料",
    "get_cftc_cot": "機構資料",
    "get_sec_filings": "監管資料",
}

CAPABILITY_PREFIXES = (
    ("regulation", "監管資料"),
    ("institutional", "機構資料"),
    ("development", "開發活躍度"),
    ("defi", "DeFi"),
    ("prediction_market", "預測市場"),
    ("derivatives", "衍生品"),
    ("market_structure", "市場結構與流動性"),
    ("onchain", "鏈上"),
    ("sentiment", "情緒"),
    ("macro", "總體經濟"),
    ("technical", "技術指標"),
    ("price", "價格"),
    ("news", "新聞與公告"),
)

DIMENSION_KEYWORDS = (
    ("監管資料", ("sec filing", "edgar", "regulation", "regulator", "court", "legislation", "執法", "監管")),
    ("機構資料", ("coin metrics", "coinmetrics", "cftc", "cot", "etf flow", "institutional", "custody", "機構持倉")),
    ("開發活躍度", ("github", "commit", "contributor", "repository", "release", "developer activity", "開發活躍")),
    ("DeFi", ("defillama", "tvl", "dex", "protocol", "lending", "stablecoin supply", "yield", "defi")),
    ("預測市場", ("polymarket", "prediction market", "contract probability", "market probability", "預測市場")),
    ("衍生品", ("funding", "open interest", "basis", "liquidation", "futures", "options", "dvol", "put/call", "deribit", "hyperliquid")),
    ("市場結構與流動性", ("orderbook", "order book", "bid-ask", "spread", "depth", "slippage", "volume profile", "market dominance", "流動性", "盤口")),
    ("鏈上", ("mempool", "etherscan", "blockscout", "helius", "xrpl", "active address", "transaction count", "onchain", "鏈上")),
    ("情緒", ("fear and greed", "fear & greed", "alternative.me", "sentiment", "情緒")),
    ("總體經濟", ("fred", "stlouisfed", "dxy", "fomc", "cpi", "interest rate", "treasury", "macro", "總體")),
    ("技術指標", ("atr", "bollinger", "adx", "z-score", "realized volatility", "correlation", "percentile", "technical", "技術指標")),
    ("價格", ("ohlcv", "klines", "spot price", "return", "price", "binance", "coingecko", "價格")),
    ("新聞與公告", ("news", "rss", "coindesk", "cointelegraph", "the block", "announcement", "新聞", "公告")),
)

PROVIDER_ALIASES = {
    "binance api": "binance",
    "binance futures": "binance",
    "binance": "binance",
    "coingecko api": "coingecko",
    "coingecko": "coingecko",
    "coin metrics": "coinmetrics",
    "coinmetrics": "coinmetrics",
    "alternative.me fear & greed": "alternative.me",
    "fear and greed index": "alternative.me",
    "fred": "fred",
    "federal reserve economic data": "fred",
    "local pandas": "local-baseline",
    "baseline csv": "local-baseline",
    "local baseline": "local-baseline",
    "google news rss": "google-news",
    "defillama": "defillama",
    "github": "github",
    "sec edgar": "sec-edgar",
    "cftc": "cftc",
}

FAILED_STATUSES = {"error", "failed", "failure", "timeout", "unavailable"}


def _normalize_failure_status(status):
    # 功能：將失敗狀態正規化，讓不同記錄層的同義狀態可穩定去重。
    normalized = str(status or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in ("failed", "failure"):
        return "error"
    if normalized == "maxturns":
        return "max_turns"
    return normalized


def _normalize_failure_reason(reason):
    # 功能：壓縮原因文字空白，避免工具內部與 dispatcher 重複記錄。
    return " ".join(str(reason or "未提供原因").split()) or "未提供原因"


def _normalize_dimension_name(value):
    # 功能：將顯示名稱、工具名稱或 capability id 正規化為允許的顯示維度。
    # 回傳：合法顯示維度；無法確定時回傳 None。
    text = str(value or "").strip()
    if text in ANALYSIS_DIMENSIONS:
        return text
    lowered = text.lower()
    if lowered in TOOL_DIMENSIONS:
        return TOOL_DIMENSIONS[lowered]
    for prefix, dimension in CAPABILITY_PREFIXES:
        if lowered == prefix or lowered.startswith(prefix + "."):
            return dimension
    return None


def classify_dimension(capability_id=None, source="", content_reference=None):
    # 功能：依固定優先序將證據分類到唯一合法分析維度。
    # 步驟：工具名稱最優先，其次 capability、結構化內容與來源 fallback。
    # 回傳：ANALYSIS_DIMENSIONS 中的一個顯示名稱。
    try:
        capability = str(capability_id or "").strip().lower()
        if capability in TOOL_DIMENSIONS:
            return TOOL_DIMENSIONS[capability]

        for prefix, dimension in CAPABILITY_PREFIXES:
            if capability == prefix or capability.startswith(prefix + "."):
                return dimension

        reference = content_reference if isinstance(content_reference, dict) else {}
        structured_parts = []
        for key in ("metric", "metrics", "data_type", "provider", "endpoint", "query", "indicator"):
            value = reference.get(key)
            if value is not None:
                structured_parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
        haystack = " ".join(structured_parts + [str(source or "")]).lower()

        for dimension, keywords in DIMENSION_KEYWORDS:
            if any(keyword in haystack for keyword in keywords):
                return dimension

        return "新聞與公告"
    except Exception:
        return "新聞與公告"


def canonicalize_source(source):
    # 功能：將 URL host 或已知非 URL provider 正規化，供獨立來源去重。
    # 步驟：URL 移除 www.；非 URL 壓縮空白並套用固定 alias。
    # 回傳：canonical source 字串，空來源回傳「未知來源」。
    try:
        raw = str(source or "").strip()
        parsed = urlparse(raw)
        if parsed.scheme.lower() in ("http", "https") and parsed.hostname:
            hostname = parsed.hostname.lower().rstrip(".")
            if hostname.startswith("www."):
                hostname = hostname[4:]
            return hostname

        normalized = re.sub(r"\s+", " ", raw.lower().replace("_", " ")).strip()
        if not normalized:
            return "未知來源"
        for alias, canonical in PROVIDER_ALIASES.items():
            if normalized == alias or alias in normalized:
                return canonical
        return normalized
    except Exception:
        return "未知來源"


def extract_cited_evidence_ids(analysis_text, evidence_list):
    # 功能：只擷取分析文字中實際出現且存在的 evidence_id。
    # 步驟：依 evidence_list 順序檢查完整 ID，並移除重複值。
    # 回傳：已引用 evidence_id 清單。
    text = str(analysis_text or "")
    cited = []
    seen = set()
    for record in evidence_list or []:
        if not isinstance(record, dict):
            continue
        evidence_id = str(record.get("evidence_id", "")).strip()
        if (
            evidence_id
            and evidence_id not in seen
            and re.search(
                r"(?<![A-Za-z0-9_-])" + re.escape(evidence_id) + r"(?![A-Za-z0-9_-])",
                text,
            )
        ):
            cited.append(evidence_id)
            seen.add(evidence_id)
    return cited


def build_analysis_summary(evidence_list, coverage=None):
    # 功能：建立忠於實際引用證據與 execution-log metadata 的多維摘要。
    # 步驟：證據去重、來源 canonicalization、維度分組，並分離資料失敗與執行限制。
    # 回傳：供報告與本機摘要使用的 dict。
    try:
        evidence_list = evidence_list if isinstance(evidence_list, list) else []
        metadata = coverage if isinstance(coverage, dict) else {}

        records_by_id = {}
        for record in evidence_list:
            if not isinstance(record, dict):
                continue
            evidence_id = str(record.get("evidence_id", "")).strip()
            if evidence_id and evidence_id not in records_by_id:
                records_by_id[evidence_id] = record

        requested_ids = metadata.get("analyzed_evidence_ids", [])
        if not isinstance(requested_ids, list):
            requested_ids = []
        analyzed_ids = []
        seen_ids = set()
        for evidence_id in requested_ids:
            evidence_id = str(evidence_id)
            if evidence_id in records_by_id and evidence_id not in seen_ids:
                analyzed_ids.append(evidence_id)
                seen_ids.add(evidence_id)

        capabilities = metadata.get("evidence_capabilities", {})
        if not isinstance(capabilities, dict):
            capabilities = {}

        dimension_details = {}
        canonical_sources = set()
        for evidence_id in analyzed_ids:
            record = records_by_id[evidence_id]
            source = canonicalize_source(record.get("source", ""))
            canonical_sources.add(source)
            dimension = classify_dimension(
                capabilities.get(evidence_id),
                record.get("source", ""),
                record.get("content_reference", {}),
            )
            detail = {
                "evidence_id": evidence_id,
                "source": source,
                "content_reference": record.get("content_reference", {}),
            }
            dimension_details.setdefault(dimension, []).append(detail)

        failed_attempts = []
        seen_failures = set()
        attempts = metadata.get("attempted_capabilities", [])
        if isinstance(attempts, list):
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                status = _normalize_failure_status(attempt.get("status"))
                if status not in FAILED_STATUSES:
                    continue
                capability = attempt.get("capability_id") or attempt.get("tool_name")
                capability_text = str(capability or "").strip()
                tool_name = capability_text.lower()
                if tool_name not in TOOL_DIMENSIONS:
                    continue
                reason = _normalize_failure_reason(
                    attempt.get("reason") or attempt.get("note")
                )
                dedup_key = (tool_name, status, reason)
                if dedup_key in seen_failures:
                    continue
                seen_failures.add(dedup_key)
                failed_attempts.append({
                    "dimension": TOOL_DIMENSIONS[tool_name],
                    "capability_id": capability_text,
                    "status": status,
                    "reason": reason,
                })

        execution_limitations = []
        seen_limitations = set()
        limitations = metadata.get("execution_limitations", [])
        if isinstance(limitations, list):
            for limitation in limitations:
                if not isinstance(limitation, dict):
                    continue
                source = str(limitation.get("source") or "agent_loop").strip()
                status = _normalize_failure_status(limitation.get("status"))
                if status not in {"timeout", "max_turns", "error"}:
                    continue
                reason = _normalize_failure_reason(
                    limitation.get("reason") or limitation.get("note")
                )
                dedup_key = (source.lower(), status, reason)
                if dedup_key in seen_limitations:
                    continue
                seen_limitations.add(dedup_key)
                execution_limitations.append({
                    "source": source,
                    "status": status,
                    "reason": reason,
                })

        relevant_omissions = []
        omissions = metadata.get("relevant_omissions", [])
        if isinstance(omissions, list):
            for omission in omissions:
                if isinstance(omission, str):
                    dimension = _normalize_dimension_name(omission)
                    if dimension:
                        relevant_omissions.append({
                            "dimension": dimension,
                            "reason": "本次未取得相關資料",
                            "confidence_impact": "可能降低相關判斷信心",
                        })
                elif isinstance(omission, dict) and omission.get("dimension"):
                    dimension = _normalize_dimension_name(omission.get("dimension"))
                    if dimension:
                        relevant_omissions.append({
                            "dimension": dimension,
                            "reason": str(omission.get("reason") or "本次未取得相關資料"),
                            "confidence_impact": str(omission.get("confidence_impact") or "可能降低相關判斷信心"),
                        })

        analyzed_dimensions = [
            dimension for dimension in ANALYSIS_DIMENSIONS if dimension in dimension_details
        ]
        return {
            "analyzed_dimensions": analyzed_dimensions,
            "cited_evidence_count": len(analyzed_ids),
            "independent_source_count": len(canonical_sources),
            "dimension_details": dimension_details,
            "failed_attempts": failed_attempts,
            "execution_limitations": execution_limitations,
            "relevant_omissions": relevant_omissions,
            "analyzed_evidence_ids": analyzed_ids,
        }
    except Exception:
        return {
            "analyzed_dimensions": [],
            "cited_evidence_count": 0,
            "independent_source_count": 0,
            "dimension_details": {},
            "failed_attempts": [],
            "execution_limitations": [],
            "relevant_omissions": [],
            "analyzed_evidence_ids": [],
        }


def render_report(run_id, question, analysis_text, evidence_list, missing_sources=None, coverage=None):
    # 功能：產出保證三章節、多維摘要與完整證據表的 Markdown 報告。
    # 步驟：解析章節、保守推導引用、加入相關限制、渲染附錄。
    # 回傳：完整 Markdown 字串；任何例外均回傳合法 fallback 報告。
    try:
        analysis_text = analysis_text or ""
        evidence_list = evidence_list if isinstance(evidence_list, list) else []
        metadata = dict(coverage) if isinstance(coverage, dict) else {}

        if "analyzed_evidence_ids" not in metadata:
            metadata["analyzed_evidence_ids"] = extract_cited_evidence_ids(
                analysis_text, evidence_list
            )

        if missing_sources:
            omissions = list(metadata.get("relevant_omissions", []))
            for source in missing_sources:
                omissions.append({
                    "dimension": str(source),
                    "reason": "呼叫端標記為與題目相關但本次未取得",
                    "confidence_impact": "可能降低相關判斷信心",
                })
            metadata["relevant_omissions"] = omissions

        summary = build_analysis_summary(evidence_list, metadata)
        judgment_content, evidence_content, confidence_content = _parse_analysis_sections(
            analysis_text
        )

        evidence_refs = _build_evidence_references(
            evidence_list, summary["analyzed_evidence_ids"]
        )
        if evidence_refs:
            evidence_content = (
                evidence_content + "\n\n" + evidence_refs
                if evidence_content else evidence_refs
            )

        limitations = _build_limitations(summary)
        if limitations:
            confidence_content = (
                confidence_content + "\n\n" + limitations
                if confidence_content else limitations
            )

        appendix = _build_analysis_appendix(summary)
        evidence_table = build_evidence_table(evidence_list) or "（本次無證據紀錄）"

        return f"""# 加密市場分析報告

> **分析問題**：{question}
> **執行編號**：{run_id}

---

## 市場判斷

{judgment_content}

---

## 關鍵依據

{evidence_content}

---

## 信心說明

{confidence_content}

---

## 附錄

### 多維度分析摘要

{appendix}

### 完整證據清單

{evidence_table}
"""
    except Exception:
        return (
            f"# 加密市場分析報告\n\n> **執行編號**：{run_id}\n\n"
            "---\n\n## 市場判斷\n\n（報告渲染時發生錯誤，無法產出完整內容）\n\n"
            "---\n\n## 關鍵依據\n\n（無法渲染）\n\n"
            "---\n\n## 信心說明\n\n（無法渲染；結論可信度無法評估）\n\n"
            "---\n\n## 附錄\n\n### 多維度分析摘要\n\n"
            "- **實際分析維度**：（無法判定）\n"
            "- **引用證據筆數**：0\n- **獨立來源數**：0\n\n"
            "### 完整證據清單\n\n（無法渲染）\n"
        )


def _build_analysis_appendix(summary):
    # 功能：將多維摘要轉為可讀 Markdown，且不產生分母或分數。
    # 回傳：摘要段落。
    dimensions = summary.get("analyzed_dimensions", [])
    lines = [
        "- **實際分析維度**：" + ("、".join(dimensions) if dimensions else "（未引用有效證據，無法判定）"),
        f"- **引用證據筆數**：{summary.get('cited_evidence_count', 0)}",
        f"- **獨立來源數**：{summary.get('independent_source_count', 0)}",
    ]

    details = summary.get("dimension_details", {})
    if details:
        lines.append("\n#### 各維度證據與來源")
        for dimension in ANALYSIS_DIMENSIONS:
            if dimension not in details:
                continue
            lines.append(f"- **{dimension}**")
            for item in details[dimension]:
                reference = json.dumps(
                    item.get("content_reference", {}),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                lines.append(
                    f"  - `{item.get('evidence_id', '')}`｜來源：{item.get('source', '未知來源')}｜內容：{reference}"
                )

    failures = summary.get("failed_attempts", [])
    if failures:
        lines.append("\n#### 已嘗試但未成功的維度")
        for failure in failures:
            lines.append(
                f"- **{failure.get('dimension')}**｜狀態：{failure.get('status', 'error')}｜原因：{failure.get('reason', '未提供原因')}"
            )

    execution_limitations = summary.get("execution_limitations", [])
    if execution_limitations:
        lines.append("\n#### 執行限制")
        for limitation in execution_limitations:
            lines.append(
                f"- **Agent 迴圈**｜狀態：{limitation.get('status', 'error')}｜原因：{limitation.get('reason', '未提供原因')}"
            )

    omissions = summary.get("relevant_omissions", [])
    if omissions:
        lines.append("\n#### 與題目相關的省略")
        for omission in omissions:
            lines.append(
                f"- **{omission.get('dimension')}**｜原因：{omission.get('reason')}｜信心影響：{omission.get('confidence_impact')}"
            )
    return "\n".join(lines)


def _build_limitations(summary):
    # 功能：將資料缺口與 Agent 執行限制分成不同信心限制段落。
    # 回傳：Markdown 限制段落；沒有相關限制時回傳空字串。
    sections = []
    data_lines = []
    for failure in summary.get("failed_attempts", []):
        data_lines.append(
            f"- {failure.get('dimension')}取得失敗（{failure.get('status')}）：{failure.get('reason')}；因此相關交叉驗證能力受限。"
        )
    for omission in summary.get("relevant_omissions", []):
        data_lines.append(
            f"- {omission.get('dimension')}：{omission.get('reason')}；信心影響：{omission.get('confidence_impact')}。"
        )
    if data_lines:
        sections.append("**相關資料限制**\n" + "\n".join(data_lines))

    execution_lines = []
    for limitation in summary.get("execution_limitations", []):
        execution_lines.append(
            f"- Agent 迴圈受限（{limitation.get('status')}）：{limitation.get('reason')}；報告僅能依停止前取得的證據整理。"
        )
    if execution_lines:
        sections.append("**執行限制**\n" + "\n".join(execution_lines))
    return "\n\n".join(sections)


def _parse_analysis_sections(analysis_text):
    # 功能：從 analysis_text 分離市場判斷、關鍵依據、信心說明。
    # 回傳：(judgment, evidence, confidence) 三個字串。
    analysis_text = str(analysis_text or "")
    markers = ["市場判斷", "關鍵依據", "信心說明"]
    pattern = r"(?:^|\n)\s*#*\s*(?:" + "|".join(markers) + r")\s*\n"
    if not re.search(pattern, analysis_text):
        return (analysis_text.strip(), "", "")

    sections = {marker: "" for marker in markers}
    positions = []
    for marker in markers:
        match = re.search(r"(?:^|\n)\s*#*\s*" + marker + r"\s*\n", analysis_text)
        if match:
            positions.append((match.start(), match.end(), marker))
    positions.sort(key=lambda item: item[0])

    for index, (_, end, marker) in enumerate(positions):
        next_start = positions[index + 1][0] if index + 1 < len(positions) else len(analysis_text)
        sections[marker] = analysis_text[end:next_start].strip()

    if positions:
        prefix = analysis_text[:positions[0][0]].strip()
        if prefix:
            sections["市場判斷"] = (
                prefix + "\n\n" + sections["市場判斷"]
                if sections["市場判斷"] else prefix
            )
    return sections["市場判斷"], sections["關鍵依據"], sections["信心說明"]


def _verification_links(record):
    # 功能：從 content_reference 選出給人閱讀的文章、圖表或資料頁。
    # API endpoint 仍保留在 evidence_list.json 供技術重現，但報告不把它當主要查證入口。
    content_ref = record.get("content_reference", {})
    source = str(record.get("source", ""))
    links = []

    if isinstance(content_ref, dict):
        for item in content_ref.get("verification_urls", []):
            if isinstance(item, dict) and item.get("url"):
                links.append((item.get("title") or "原文", item["url"]))
        for item in content_ref.get("human_urls", []):
            if isinstance(item, dict) and item.get("url"):
                links.append((item.get("label") or "資料頁", item["url"]))
        if content_ref.get("human_url"):
            links.append(("互動資料頁", content_ref["human_url"]))
        if not links:
            for item in content_ref.get("items", [])[:3]:
                if isinstance(item, dict) and item.get("url"):
                    links.append((item.get("title") or "原文", item["url"]))

    source_lower = source.lower()
    if not links and "alternative.me" in source_lower:
        links.append(("Fear & Greed Index", "https://alternative.me/crypto/fear-and-greed-index/"))
    elif not links and "stlouisfed.org/fred" in source_lower:
        series_ids = content_ref.get("fred_series_ids", []) if isinstance(content_ref, dict) else []
        links.extend((series_id, f"https://fred.stlouisfed.org/series/{series_id}") for series_id in series_ids)
    elif not links and "mempool.space" in source_lower:
        links.append(("mempool.space 區塊瀏覽器", "https://mempool.space/"))
    elif not links and "etherscan" in source_lower:
        links.append(("Etherscan 區塊瀏覽器", "https://etherscan.io/"))
    elif not links and "blockscout" in source_lower:
        links.append(("BNB Chain 區塊瀏覽器", "https://bscscan.com/"))
    elif not links and "helius" in source_lower:
        links.append(("Solscan 區塊瀏覽器", "https://solscan.io/"))
    elif not links and ("xrpl" in source_lower or "ripple" in source_lower):
        links.append(("XRPScan 區塊瀏覽器", "https://xrpscan.com/"))
    elif not links and source.startswith("http") and "/api" not in source_lower and "api." not in source_lower:
        links.append(("來源頁面", source))

    unique = []
    seen = set()
    for label, url in links:
        if url and url not in seen:
            seen.add(url)
            unique.append((str(label), str(url)))
    return unique[:5]


def _format_verification_links(record, limit=3):
    links = _verification_links(record)[:limit]
    if not links:
        source = str(record.get("source", "")).strip()
        # Provider 名稱等非 URL 標籤可直接呈現；技術 endpoint 仍只留在 evidence JSON。
        if source and not source.lower().startswith(("http://", "https://")):
            return source
        return "技術來源詳見 evidence_list.json"
    formatted = []
    for label, url in links:
        safe_label = label.replace("[", "").replace("]", "").replace("|", "／")
        formatted.append(f"[{safe_label}]({url})")
    return "、".join(formatted)


def _build_evidence_references(evidence_list, analyzed_evidence_ids=None):
    # 功能：只為實際引用的證據建立補充引用，附帶人類可讀查證連結。
    # 回傳：Markdown 引用列表。
    analyzed = set(analyzed_evidence_ids or [])
    if not analyzed:
        return ""
    lines = []
    seen = set()
    for record in evidence_list or []:
        if not isinstance(record, dict):
            continue
        evidence_id = str(record.get("evidence_id", ""))
        if evidence_id not in analyzed or evidence_id in seen:
            continue
        seen.add(evidence_id)
        claim = record.get("related_claim", "")
        verification = _format_verification_links(record)
        lines.append(f"- **[{evidence_id}]** {claim}｜查證：{verification}")
    return "\n".join(lines)


def build_evidence_table(evidence_list):
    # 功能：把完整證據清單轉成 Markdown 表格。
    # 步驟：保留 C2 欄位，不因是否引用而刪除蒐集紀錄。
    # 回傳：Markdown 表格字串。
    try:
        if not evidence_list:
            return ""
        rows = [
            "| evidence_id | 人類可讀查證來源 | 取得時間 | 對應判斷 |",
            "|-------------|------------------|----------|----------|",
        ]
        for record in evidence_list:
            record = record if isinstance(record, dict) else {}
            evidence_id = _escape_pipe(str(record.get("evidence_id", "")))
            verification = _escape_pipe(_format_verification_links(record))
            fetched_at = _escape_pipe(str(record.get("fetched_at", "")))
            related_claim = _escape_pipe(str(record.get("related_claim", "")))
            rows.append(
                f"| {evidence_id} | {verification} | {fetched_at} | {related_claim} |"
            )
        return "\n".join(rows)
    except Exception:
        return ""


def _escape_pipe(value):
    # 功能：跳脫 Markdown 表格中的管線字元。
    # 回傳：跳脫後字串。
    return value.replace("|", "\\|")


# ─── C7 Integration ──────────────────────────────────────────────────────────

def generate_report_data(question_type, symbols, analysis_text, evidence_list,
                         execution_log=None, series=None):
    """Generate C7 report_data.json content.

    Fails gracefully: returns None and logs error to execution_log.
    Does NOT block the original three deliverables (report.md, evidence, log).

    Args:
        question_type: "single_integration" | "hypothesis" | "comparison"
        symbols: e.g. ["BTC"] or ["BTC", "ETH"]
        analysis_text: Agent's analysis output
        evidence_list: C2 evidence records
        execution_log: Mutable list for error logging
        series: Dict of time-series for chart rendering

    Returns:
        dict (valid C7) or None on failure.
    """
    try:
        return _c7_build_report_data(
            question_type=question_type,
            symbols=symbols,
            analysis_text=analysis_text,
            evidence_list=evidence_list,
            execution_log=execution_log,
            series=series,
        )
    except Exception as exc:
        if isinstance(execution_log, list):
            execution_log.append({
                "tool_name": "generate_report_data",
                "status": "error",
                "note": f"C7 generation failed: {exc}",
            })
        return None
