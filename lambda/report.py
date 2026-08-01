"""
report.py — 決定性 Renderer（第 4.5 節）

接收 ReportModel JSON 結構，用程式保證固定的三章節 + 附錄格式。
不再依賴正規表示式從自由 Markdown 中拆章。
前端只看到最終 Markdown 字串，不接觸 ReportModel 內部結構。
"""


def render_report(run_id, question, report_model, evidence_list, missing_sources=None):
    """從 ReportModel dict 渲染出完整 Markdown 報告。

    參數：
        run_id: 執行 ID
        question: 使用者原始問題
        report_model: Synthesis Agent 產出的 ReportModel dict
        evidence_list: 全域 evidence_list
        missing_sources: 缺少的資料類別清單

    回傳：完整 Markdown 字串（三章節保證存在）
    """
    try:
        report_model = report_model or {}
        evidence_list = evidence_list or []
        missing_sources = missing_sources or []

        # 從 ReportModel 各欄位渲染各章節
        judgment_section = _render_judgment(report_model)
        evidence_section = _render_key_evidence(report_model, evidence_list)
        confidence_section = _render_confidence(report_model, missing_sources)

        # 計算覆蓋率
        coverage_pct, obtained_categories, missing_categories = calculate_coverage(evidence_list)
        obtained_str = "、".join(obtained_categories) if obtained_categories else "（無）"
        missing_cat_str = "、".join(missing_categories) if missing_categories else "（無）"

        # 完整證據表
        evidence_table = build_evidence_table(evidence_list)

        # 用 f-string 模板保證三章節標題一定存在
        report = f"""# 加密市場分析報告

> **分析問題**：{question}
> **執行編號**：{run_id}

---

## 市場判斷

{judgment_section}

---

## 關鍵依據

{evidence_section}

---

## 信心說明

{confidence_section}

---

## 附錄

### 資料覆蓋率

- **覆蓋率**：{coverage_pct:.1f}%
- **已取得類別**：{obtained_str}
- **缺少類別**：{missing_cat_str}

### 完整證據清單

{evidence_table}
"""
        return report

    except Exception:
        # 任何例外仍回傳最低限度的報告，保證三章節標題存在
        return (
            f"# 加密市場分析報告\n\n"
            f"> **執行編號**：{run_id}\n\n"
            f"---\n\n## 市場判斷\n\n（報告渲染時發生錯誤，無法產出完整內容）\n\n"
            f"---\n\n## 關鍵依據\n\n（無法渲染）\n\n"
            f"---\n\n## 信心說明\n\n（無法渲染）\n"
        )


def _render_judgment(report_model):
    """從 ReportModel 渲染市場判斷章節。"""
    parts = []

    # 市場狀態概述
    market_state = report_model.get("market_state", {})
    regime = market_state.get("regime", "無法判斷")
    confidence = market_state.get("confidence", "low")
    time_horizon = market_state.get("time_horizon", "")

    confidence_label = {"low": "低", "medium": "中", "high": "高"}.get(confidence, confidence)
    parts.append(f"**市場狀態**：{regime}")
    parts.append(f"**分析信心**：{confidence_label}　｜　**時間範圍**：{time_horizon}")
    parts.append("")

    # 關鍵發現（分層：fact → inference → conclusion）
    key_findings = report_model.get("key_findings", [])
    if key_findings:
        # 按 layer 分組
        facts = [f for f in key_findings if f.get("layer") == "fact"]
        inferences = [f for f in key_findings if f.get("layer") == "inference"]
        conclusions = [f for f in key_findings if f.get("layer") == "conclusion"]

        if facts:
            parts.append("### 事實觀察")
            for f in facts:
                eids = ", ".join(f.get("evidence_ids", [])) if f.get("evidence_ids") else ""
                eid_ref = f" `[{eids}]`" if eids else ""
                parts.append(f"- {f.get('statement', '')}{eid_ref}")
            parts.append("")

        if inferences:
            parts.append("### 推論")
            for f in inferences:
                eids = ", ".join(f.get("evidence_ids", [])) if f.get("evidence_ids") else ""
                eid_ref = f" `[{eids}]`" if eids else ""
                parts.append(f"- {f.get('statement', '')}{eid_ref}")
            parts.append("")

        if conclusions:
            parts.append("### 結論")
            for f in conclusions:
                eids = ", ".join(f.get("evidence_ids", [])) if f.get("evidence_ids") else ""
                eid_ref = f" `[{eids}]`" if eids else ""
                parts.append(f"- {f.get('statement', '')}{eid_ref}")
            parts.append("")

    # 觸發因子
    catalysts = report_model.get("catalysts", [])
    if catalysts:
        parts.append("### 潛在觸發因子")
        for c in catalysts:
            parts.append(f"- {c}")
        parts.append("")

    return "\n".join(parts) if parts else "（無法產出市場判斷）"


def _render_key_evidence(report_model, evidence_list):
    """從 ReportModel 渲染關鍵依據章節。"""
    parts = []

    # 支持訊號
    supporting = report_model.get("supporting_signals", [])
    if supporting:
        parts.append("### 支持訊號")
        for s in supporting:
            direction = s.get("direction", "neutral")
            desc = s.get("description", "")
            eids = ", ".join(s.get("evidence_ids", [])) if s.get("evidence_ids") else ""
            eid_ref = f" `[{eids}]`" if eids else ""
            icon = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(direction, "")
            parts.append(f"- {icon} {desc}{eid_ref}")
        parts.append("")

    # 矛盾訊號
    contradicting = report_model.get("contradicting_signals", [])
    if contradicting:
        parts.append("### 矛盾訊號")
        for s in contradicting:
            direction = s.get("direction", "neutral")
            desc = s.get("description", "")
            resolution = s.get("resolution", "")
            eids = ", ".join(s.get("evidence_ids", [])) if s.get("evidence_ids") else ""
            eid_ref = f" `[{eids}]`" if eids else ""
            icon = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(direction, "")
            line = f"- {icon} {desc}{eid_ref}"
            if resolution:
                line += f"\n  - 取捨依據：{resolution}"
            parts.append(line)
        parts.append("")

    # 證據引用清單
    evidence_ids_used = report_model.get("evidence_ids", [])
    if evidence_ids_used and evidence_list:
        parts.append("### 引用證據對照")
        eid_map = {r.get("evidence_id"): r for r in evidence_list}
        for eid in evidence_ids_used:
            record = eid_map.get(eid, {})
            source = record.get("source", "未知來源")
            claim = record.get("related_claim", "")
            parts.append(f"- **[{eid[:12]}...]** {source}：{claim}")
        parts.append("")

    if not parts:
        parts.append("（本次分析未能產出結構化的關鍵依據）")

    return "\n".join(parts)


def _render_confidence(report_model, missing_sources):
    """從 ReportModel 渲染信心說明章節。"""
    parts = []

    market_state = report_model.get("market_state", {})
    confidence = market_state.get("confidence", "low")
    confidence_label = {"low": "低", "medium": "中", "high": "高"}.get(confidence, confidence)
    parts.append(f"**整體信心程度**：{confidence_label}")
    parts.append("")

    # 風險因子
    risks = report_model.get("risks", [])
    if risks:
        parts.append("### 主要風險")
        for r in risks:
            parts.append(f"- {r}")
        parts.append("")

    # 推翻條件
    invalidation = report_model.get("invalidation_conditions", [])
    if invalidation:
        parts.append("### 推翻條件")
        for i in invalidation:
            parts.append(f"- {i}")
        parts.append("")

    # 關注事項
    watch_items = report_model.get("watch_items", [])
    if watch_items:
        parts.append("### 短期關注事項")
        for w in watch_items:
            parts.append(f"- {w}")
        parts.append("")

    # 限制說明
    limitations = report_model.get("limitations", [])
    if limitations or missing_sources:
        parts.append("### 已知限制")
        for l in limitations:
            parts.append(f"- {l}")
        if missing_sources:
            sources_str = "、".join(missing_sources)
            parts.append(f"- 未能取得的資料類別：{sources_str}")
        parts.append("")

    if not parts:
        parts.append("（無法產出信心說明）")

    return "\n".join(parts)


def build_evidence_table(evidence_list):
    """把證據清單轉成 Markdown 表格，附加在報告附錄。"""
    try:
        if not evidence_list:
            return ""

        header = "| evidence_id | 來源 | 取得時間 | 對應判斷 |"
        separator = "|-------------|------|----------|----------|"
        rows = [header, separator]

        for record in evidence_list:
            eid = _escape_pipe(str(record.get("evidence_id", "")))
            source = _escape_pipe(str(record.get("source", "")))
            fetched_at = _escape_pipe(str(record.get("fetched_at", "")))
            related_claim = _escape_pipe(str(record.get("related_claim", "")))
            rows.append(f"| {eid} | {source} | {fetched_at} | {related_claim} |")

        return "\n".join(rows)
    except Exception:
        return ""


def _escape_pipe(value):
    """跳脫 Markdown 表格中的管線字元。"""
    return value.replace("|", "\\|")


def calculate_coverage(evidence_list):
    """計算資料覆蓋率。

    回傳：(覆蓋率百分比, 已取得的類別清單, 缺少的類別清單)
    """
    category_keywords = {
        "價格": ["binance", "coingecko", "klines", "ohlcv", "price", "baseline", "local_pandas"],
        "新聞": ["cryptopanic", "news", "rss", "github"],
        "鏈上": ["mempool", "etherscan", "blockscout", "helius", "xrpl", "onchain"],
        "情緒": ["alternative.me", "fear", "greed", "sentiment"],
        "總經": ["fred", "macro", "stlouisfed"],
    }

    found_categories = set()
    for record in (evidence_list or []):
        source_lower = str(record.get("source", "")).lower()
        for category, keywords in category_keywords.items():
            if any(kw in source_lower for kw in keywords):
                found_categories.add(category)

    all_categories = list(category_keywords.keys())
    obtained = sorted(found_categories)
    missing = sorted(set(all_categories) - found_categories)
    coverage_pct = (len(obtained) / len(all_categories)) * 100

    return (coverage_pct, obtained, missing)
