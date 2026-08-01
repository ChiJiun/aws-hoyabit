"""
export.py — 交付物匯出與自我檢查

把執行期間累積的證據與日誌，轉成命題要求的檔案格式。
validate_before_export 實現命題評分觀察點的程式化驗證。
"""

import json
import re


# 禁止出現的投資建議語句模式
FORBIDDEN_PATTERNS = [
    r"買進", r"賣出", r"買入", r"做多", r"做空",
    r"目標價", r"目標位", r"建議持有", r"建議買",
    r"建議賣", r"加倉", r"減倉", r"止損", r"止盈",
    r"進場", r"出場", r"建倉", r"清倉",
    r"buy", r"sell", r"long", r"short",
    r"target\s*price", r"price\s*target",
]

# 資料來源類別對應的工具名稱
SOURCE_CATEGORY_MAP = {
    "get_price_ohlcv": "價格",
    "compute_quant": "價格",
    "search_news": "新聞",
    "get_onchain": "鏈上",
    "get_sentiment": "情緒",
    "get_macro": "總經",
}


def export_evidence_list(evidence_list, as_csv=False):
    """把證據清單轉成可繳交的檔案內容。

    預設 JSON 格式；as_csv=True 時輸出 CSV。
    回傳：字串（可直接交給 storage.save_output_file 上傳）。
    """
    if as_csv:
        # CSV 格式
        lines = ["evidence_id,source,fetched_at,content_reference,related_claim"]
        for record in evidence_list:
            # content_reference 轉為 JSON 字串，用雙引號包裹避免逗號問題
            cr = json.dumps(record.get("content_reference", {}), ensure_ascii=False)
            line = ','.join([
                record.get("evidence_id", ""),
                record.get("source", ""),
                record.get("fetched_at", ""),
                f'"{cr}"',
                f'"{record.get("related_claim", "")}"',
            ])
            lines.append(line)
        return "\n".join(lines)
    else:
        # JSON 格式
        return json.dumps(evidence_list, ensure_ascii=False, indent=2)


def export_execution_log(execution_log):
    """把執行紀錄轉成 JSONL 格式（每行一筆 JSON）。

    回傳：字串。
    """
    lines = []
    for record in execution_log:
        lines.append(json.dumps(record, ensure_ascii=False))
    return "\n".join(lines)


def validate_before_export(evidence_list, analysis_text):
    """交付前的自我檢查。

    檢查項目：
      1. 每筆證據的四個必填欄位是否齊備
      2. 資料來源類別數是否 >= 3
      3. 是否有付費來源被當成唯一依據（只有一個來源類別）
      4. 報告中是否出現投資建議語句

    回傳：(是否全數通過, 未通過項目的清單)。
    """
    issues = []

    # 檢查 1：四欄位齊備
    required_fields = ["source", "fetched_at", "content_reference", "related_claim"]
    for i, record in enumerate(evidence_list):
        for field in required_fields:
            if not record.get(field):
                issues.append(f"證據 #{i+1} 缺少欄位：{field}")

    # 檢查 2：來源類別數 >= 3
    categories = set()
    for record in evidence_list:
        source = record.get("source", "")
        # 從 evidence_id 關聯的工具名稱推斷類別
        # 但 evidence record 裡沒有 tool_name，改從 source 推斷
        if "binance" in source.lower() or "coingecko" in source.lower() or "pandas" in source.lower() or "baseline" in source.lower():
            categories.add("價格")
        elif "cryptopanic" in source.lower() or "rss" in source.lower() or "github" in source.lower():
            categories.add("新聞")
        elif "mempool" in source.lower() or "etherscan" in source.lower() or "blockscout" in source.lower() or "helius" in source.lower() or "xrpl" in source.lower():
            categories.add("鏈上")
        elif "alternative.me" in source.lower() or "fear" in source.lower():
            categories.add("情緒")
        elif "fred" in source.lower():
            categories.add("總經")
        elif "local_pandas_computation" in source.lower():
            categories.add("價格")  # quant 工具屬於價格類
        else:
            categories.add("其他")

    if len(categories) < 3:
        issues.append(
            f"來源類別數不足：僅有 {len(categories)} 類（{', '.join(categories)}），需至少 3 類"
        )

    # 檢查 3：付費來源是否為唯一依據
    if len(categories) == 1:
        issues.append("所有證據來自同一類別，可能存在單一來源依賴問題")

    # 檢查 4：投資建議語句
    if analysis_text:
        text_lower = analysis_text.lower()
        found_forbidden = []
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, text_lower):
                found_forbidden.append(pattern)
        if found_forbidden:
            issues.append(
                f"報告中出現疑似投資建議語句：{', '.join(found_forbidden[:5])}"
            )

    passed = len(issues) == 0
    return passed, issues
