"""
report.py — 報告渲染

把模型的分析內容套進固定的 Markdown 模板。渲染由程式負責、不交給模型，
這樣可以保證命題要求的三個章節一定存在。
"""

from datetime import datetime, timezone


# 預期的資料類別（用於計算覆蓋率）
EXPECTED_CATEGORIES = ["價格", "新聞", "鏈上", "情緒", "總經"]


def calculate_coverage(evidence_list):
    """計算資料覆蓋率，作為報告中信心等級的客觀依據。

    統計 evidence_list 中出現了幾種不同的資料類別。
    回傳：(覆蓋率百分比, 已取得的類別清單, 缺少的類別清單)
    """
    got_categories = set()

    for record in evidence_list:
        source = record.get("source", "").lower()

        if "binance" in source or "coingecko" in source or "baseline" in source:
            got_categories.add("價格")
        elif "local_pandas_computation" in source:
            got_categories.add("價格")
        elif "cryptopanic" in source or "rss" in source or "github" in source:
            got_categories.add("新聞")
        elif any(kw in source for kw in ["mempool", "etherscan", "blockscout", "helius", "xrpl"]):
            got_categories.add("鏈上")
        elif "alternative.me" in source or "fear" in source:
            got_categories.add("情緒")
        elif "fred" in source:
            got_categories.add("總經")

    got_list = sorted(got_categories)
    missing_list = [c for c in EXPECTED_CATEGORIES if c not in got_categories]
    coverage_pct = len(got_categories) / len(EXPECTED_CATEGORIES) * 100

    return coverage_pct, got_list, missing_list


def build_evidence_table(evidence_list):
    """把證據清單轉成 Markdown 表格，附加在報告附錄。

    欄位：evidence_id、來源、取得時間、對應判斷。
    回傳：Markdown 表格字串。
    """
    if not evidence_list:
        return "（無證據記錄）"

    lines = [
        "| # | Evidence ID | 來源 | 取得時間 | 對應判斷 |",
        "|---|-------------|------|----------|----------|",
    ]

    for i, record in enumerate(evidence_list, 1):
        eid = record.get("evidence_id", "N/A")[:8] + "..."
        source = record.get("source", "N/A")
        # 截斷過長的 source
        if len(source) > 40:
            source = source[:37] + "..."
        fetched_at = record.get("fetched_at", "N/A")
        # 只取日期時間部分
        if "T" in fetched_at:
            fetched_at = fetched_at.split("T")[0] + " " + fetched_at.split("T")[1][:8]
        claim = record.get("related_claim", "N/A")
        # 截斷過長的 claim
        if len(claim) > 50:
            claim = claim[:47] + "..."

        lines.append(f"| {i} | `{eid}` | {source} | {fetched_at} | {claim} |")

    return "\n".join(lines)


def render_report(run_id, question, analysis_text, evidence_list, missing_sources=None):
    """產出最終的 Markdown 分析報告。

    模板結構保證命題要求的三個章節一定存在：
      1. 市場判斷
      2. 關鍵依據
      3. 信心說明
    加上附錄：資料覆蓋率、完整證據清單。

    回傳：完整的 Markdown 字串。
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    coverage_pct, got_categories, missing_categories = calculate_coverage(evidence_list)

    # 處理 missing_sources 參數
    if missing_sources is None:
        missing_sources = missing_categories

    # 組建限制段落
    limitations = []
    if missing_sources:
        limitations.append(f"本次分析未能取得以下類別的資料：{', '.join(missing_sources)}。")
    limitations.append("本報告為資訊提煉工具的產出，不構成任何投資建議。")

    limitations_text = "\n".join(f"- {lim}" for lim in limitations)

    # 組建證據表格
    evidence_table = build_evidence_table(evidence_list)

    # 使用 f-string 模板保證三章節存在
    report_md = f"""# 加密市場分析報告

> **分析題目**：{question}
> **執行 ID**：{run_id}
> **產出時間**：{now}

---

## 市場判斷

{_extract_section(analysis_text, "市場判斷", "本節內容由 AI Agent 基於多源資料分析產生。")}

---

## 關鍵依據

{_extract_section(analysis_text, "關鍵依據", "（依據列表待模型填充）")}

---

## 信心說明

{_extract_section(analysis_text, "信心說明", "（信心說明待模型填充）")}

### 已知限制

{limitations_text}

---

## 附錄：資料覆蓋率

- 覆蓋率：**{coverage_pct:.0f}%**（{len(got_categories)}/{len(EXPECTED_CATEGORIES)} 類別）
- 已取得：{', '.join(got_categories) if got_categories else '無'}
- 缺少：{', '.join(missing_sources) if missing_sources else '無'}

## 附錄：完整證據清單

{evidence_table}

---

*本報告由 HOYA BIT 加密市場分析系統自動產出，僅供資訊參考，不構成投資建議。*
"""
    return report_md


def _extract_section(analysis_text, section_name, fallback):
    """從模型產出的分析文字中擷取指定章節內容。

    若模型已按格式輸出（含 ## 市場判斷 等標題），則擷取對應段落。
    若未按格式，則整段放入第一章節，其餘用 fallback。
    """
    if not analysis_text:
        return fallback

    # 嘗試按 ## 標題切割
    # 找到 "## {section_name}" 或 "# {section_name}" 開始的段落
    patterns = [f"## {section_name}", f"# {section_name}", f"**{section_name}**"]

    for pattern in patterns:
        if pattern in analysis_text:
            # 找到開始位置
            start_idx = analysis_text.index(pattern) + len(pattern)
            # 找到下一個 ## 或文件結尾
            remaining = analysis_text[start_idx:]
            # 尋找下一個章節標題
            next_section = _find_next_heading(remaining)
            if next_section >= 0:
                content = remaining[:next_section].strip()
            else:
                content = remaining.strip()

            return content if content else fallback

    # 如果沒找到對應標題，第一個章節放全文，其餘用 fallback
    if section_name == "市場判斷":
        return analysis_text
    else:
        return fallback


def _find_next_heading(text):
    """在文字中找到下一個 Markdown 標題的位置。"""
    lines = text.split("\n")
    pos = 0
    for i, line in enumerate(lines):
        if i == 0:
            pos += len(line) + 1
            continue
        if line.startswith("## ") or line.startswith("# "):
            return pos - len(line) - 1
        pos += len(line) + 1
    return -1
