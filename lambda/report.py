"""
report.py — 報告渲染

把模型的分析內容套進固定的 Markdown 模板。渲染由程式負責、不交給模型，
這樣可以保證命題要求的三個章節一定存在。
"""


def render_report(run_id, question, analysis_text, evidence_list, missing_sources=None):
    # 功能：產出最終的 Markdown 分析報告。
    # 模板結構（對應命題「分析報告至少需包含」的三項要求）：
    #   1. 結論／市場判斷
    #   2. 關鍵依據        —— 每條附對應的 evidence_id，說明該證據如何支撐判斷
    #   3. 信心說明        —— 判斷信心、已知限制、資料不足之處、可能推翻結論的條件
    #   附錄：資料覆蓋率   —— 成功取得的資料類別 ÷ 原本計畫的資料類別
    #   附錄：完整證據清單
    # 參數 missing_sources：本次執行未能取得的資料類別，會寫進限制段落。
    # 實作：用 f-string 拼接字串即可，不需要額外的模板套件。
    # 回傳：完整的 Markdown 字串
    try:
        # 步驟：安全處理輸入參數預設值
        analysis_text = analysis_text or ""
        evidence_list = evidence_list or []
        missing_sources = missing_sources or []

        # 步驟：解析 analysis_text，嘗試從中分離三段內容
        judgment_content, evidence_content, confidence_content = _parse_analysis_sections(analysis_text)

        # 步驟：為關鍵依據段落附加 evidence_id 引用
        evidence_refs = _build_evidence_references(evidence_list)
        if evidence_refs:
            evidence_content = evidence_content + "\n\n" + evidence_refs if evidence_content else evidence_refs

        # 步驟：組裝 missing_sources 限制段落
        limitation_paragraph = ""
        if missing_sources:
            sources_str = "、".join(missing_sources)
            limitation_paragraph = f"\n\n> ⚠️ **資料不足警示**：本次分析未能取得以下資料類別：{sources_str}。相關結論可能因資料缺失而存在偏差。"

        # 步驟：計算覆蓋率供附錄使用
        coverage_pct, obtained_categories, missing_categories = calculate_coverage(evidence_list)
        obtained_str = "、".join(obtained_categories) if obtained_categories else "（無）"
        missing_cat_str = "、".join(missing_categories) if missing_categories else "（無）"

        # 步驟：建立完整證據表
        evidence_table = build_evidence_table(evidence_list)

        # 步驟：用 f-string 模板保證三章節標題一定存在
        report = f"""# 加密市場分析報告

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

{confidence_content}{limitation_paragraph}

---

## 附錄

### 資料覆蓋率

- **覆蓋率**：{coverage_pct:.1f}%
- **已取得類別**：{obtained_str}
- **缺少類別**：{missing_cat_str}

### 完整證據清單

{evidence_table}
"""
        # 回傳：完整 Markdown 字串
        return report

    except Exception:
        # 步驟：任何例外仍回傳最低限度的報告，保證三章節標題存在
        return (
            f"# 加密市場分析報告\n\n"
            f"> **執行編號**：{run_id}\n\n"
            f"---\n\n## 市場判斷\n\n（報告渲染時發生錯誤，無法產出完整內容）\n\n"
            f"---\n\n## 關鍵依據\n\n（無法渲染）\n\n"
            f"---\n\n## 信心說明\n\n（無法渲染）\n"
        )


def _parse_analysis_sections(analysis_text):
    # 功能：從 LLM 產出的 analysis_text 中分離三段內容。
    #       若包含「市場判斷」「關鍵依據」「信心說明」標記則各自提取；
    #       否則整段放入市場判斷。
    # 回傳：(judgment, evidence, confidence) 三個字串

    # 步驟：定義章節標記（支援有無 # 或 ## 前綴）
    import re

    markers = ["市場判斷", "關鍵依據", "信心說明"]
    pattern = r"(?:^|\n)\s*#*\s*(?:" + "|".join(markers) + r")\s*\n"

    if not re.search(pattern, analysis_text):
        # 步驟：analysis_text 沒有章節標記，整段視為市場判斷
        return (analysis_text.strip(), "", "")

    # 步驟：依序切割各章節
    sections = {"市場判斷": "", "關鍵依據": "", "信心說明": ""}
    # 用更精準的正則找出各章節起始位置
    section_positions = []
    for marker in markers:
        match = re.search(r"(?:^|\n)\s*#*\s*" + marker + r"\s*\n", analysis_text)
        if match:
            section_positions.append((match.start(), match.end(), marker))

    # 按位置排序
    section_positions.sort(key=lambda x: x[0])

    for i, (start, end, marker) in enumerate(section_positions):
        # 該段內容從 end 到下一段 start（或文末）
        next_start = section_positions[i + 1][0] if i + 1 < len(section_positions) else len(analysis_text)
        sections[marker] = analysis_text[end:next_start].strip()

    # 若有在第一個章節前的文字，併入市場判斷
    if section_positions:
        prefix = analysis_text[:section_positions[0][0]].strip()
        if prefix:
            sections["市場判斷"] = prefix + "\n\n" + sections["市場判斷"] if sections["市場判斷"] else prefix

    return (sections["市場判斷"], sections["關鍵依據"], sections["信心說明"])


def _build_evidence_references(evidence_list):
    # 功能：為關鍵依據章節產生每條證據的引用列表。
    # 回傳：Markdown 列表字串，每行 `- [evidence_id] source: related_claim`
    if not evidence_list:
        return ""

    lines = []
    for record in evidence_list:
        eid = record.get("evidence_id", "N/A")
        source = record.get("source", "未知來源")
        claim = record.get("related_claim", "")
        lines.append(f"- **[{eid}]** {source}：{claim}")

    return "\n".join(lines)


def build_evidence_table(evidence_list):
    # 功能：把證據清單轉成 Markdown 表格，附加在報告附錄。
    # 欄位：evidence_id、來源、取得時間、對應判斷。
    # 回傳：Markdown 表格字串
    try:
        # 步驟：處理空值或空清單
        if not evidence_list:
            return ""

        # 步驟：建立表頭
        header = "| evidence_id | 來源 | 取得時間 | 對應判斷 |"
        separator = "|-------------|------|----------|----------|"
        rows = [header, separator]

        # 步驟：逐筆證據產生表格列
        for record in evidence_list:
            eid = _escape_pipe(str(record.get("evidence_id", "")))
            source = _escape_pipe(str(record.get("source", "")))
            fetched_at = _escape_pipe(str(record.get("fetched_at", "")))
            related_claim = _escape_pipe(str(record.get("related_claim", "")))
            rows.append(f"| {eid} | {source} | {fetched_at} | {related_claim} |")

        # 回傳：完整 Markdown 表格字串
        return "\n".join(rows)
    except Exception:
        # 步驟：任何例外回傳空字串，不讓未處理的例外逸出
        return ""


def _escape_pipe(value):
    # 功能：跳脫 Markdown 表格中的管線字元，避免破壞表格結構。
    # 回傳：跳脫後的字串
    return value.replace("|", "\\|")


def calculate_coverage(evidence_list):
    # 功能：計算資料覆蓋率，作為報告中信心等級的客觀依據。
    # 實作：統計 evidence_list 中出現了幾種不同的資料類別
    #      （價格、新聞、鏈上、情緒、總經），除以預期的類別總數。
    # 回傳：(覆蓋率百分比, 已取得的類別清單, 缺少的類別清單)

    # 五種預期類別及其關鍵字對應
    category_keywords = {
        "價格": ["binance", "coingecko", "klines", "ohlcv", "price", "baseline", "local_pandas"],
        "新聞": ["cryptopanic", "news", "rss", "github"],
        "鏈上": ["mempool", "etherscan", "blockscout", "helius", "xrpl", "onchain"],
        "情緒": ["alternative.me", "fear", "greed", "sentiment"],
        "總經": ["fred", "macro", "stlouisfed"],
    }

    # 步驟：掃描每筆證據的 source 欄位，比對關鍵字歸類
    found_categories = set()
    for record in (evidence_list or []):
        source_lower = str(record.get("source", "")).lower()
        for category, keywords in category_keywords.items():
            if any(kw in source_lower for kw in keywords):
                found_categories.add(category)

    # 步驟：計算覆蓋率
    all_categories = list(category_keywords.keys())
    obtained = sorted(found_categories)
    missing = sorted(set(all_categories) - found_categories)
    coverage_pct = (len(obtained) / len(all_categories)) * 100

    # 回傳：(覆蓋率百分比, 已取得類別清單, 缺少類別清單)
    return (coverage_pct, obtained, missing)