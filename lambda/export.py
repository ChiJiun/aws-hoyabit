"""
export.py — 交付物匯出與自我檢查

把執行期間累積的證據與日誌，轉成命題要求的檔案格式。
C7 report_data 成功時由 export_report_data() 輸出 JSON。
"""

import json
import csv
import io


def export_evidence_list(evidence_list, as_csv=False):
    # 功能：把證據清單轉成可繳交的檔案內容。
    # 格式：預設 JSON（每筆含 evidence_id、source、fetched_at、content_reference、related_claim）；
    #      as_csv=True 時輸出 CSV 格式。
    # 回傳：字串（可直接交給 storage.save_output_file 上傳）
    try:
        # 邊界情況：空清單
        if not evidence_list:
            if as_csv:
                # 空清單時仍輸出標題列
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["evidence_id", "source", "fetched_at", "content_reference", "related_claim"])
                return output.getvalue()
            else:
                return json.dumps([], ensure_ascii=False, indent=2)

        if as_csv:
            # CSV 格式輸出
            output = io.StringIO()
            writer = csv.writer(output)
            # 寫入標題列
            writer.writerow(["evidence_id", "source", "fetched_at", "content_reference", "related_claim"])
            # 逐筆寫入資料
            for record in evidence_list:
                # content_reference 是 dict，序列化為 JSON 字串放入 CSV 欄位
                content_ref = json.dumps(record.get("content_reference", {}), ensure_ascii=False)
                writer.writerow([
                    record.get("evidence_id", ""),
                    record.get("source", ""),
                    record.get("fetched_at", ""),
                    content_ref,
                    record.get("related_claim", ""),
                ])
            return output.getvalue()
        else:
            # JSON 格式：保留命題必要五欄位，並輸出可回溯品質與封存欄位。
            exported = []
            optional_fields = [
                "schema_version", "tool_name", "source_url", "data_quality",
                "anomaly_flags", "raw_payload_path", "raw_payload_sha256",
                "archive_status", "archive_error",
            ]
            for record in evidence_list:
                item = {
                    "evidence_id": record.get("evidence_id", ""),
                    "source": record.get("source", ""),
                    "fetched_at": record.get("fetched_at", ""),
                    "content_reference": record.get("content_reference", {}),
                    "related_claim": record.get("related_claim", ""),
                }
                for field in optional_fields:
                    if field in record:
                        item[field] = record.get(field)
                exported.append(item)
            return json.dumps(exported, ensure_ascii=False, indent=2)
    except Exception:
        # 永不讓未處理例外逸出
        if as_csv:
            return "evidence_id,source,fetched_at,content_reference,related_claim\n"
        else:
            return json.dumps([], ensure_ascii=False)


def export_execution_log(execution_log):
    # 功能：把執行紀錄轉成 JSONL 格式（每行一筆 JSON）。
    # 內容：時間戳記、工具呼叫、資料取得紀錄、分析流程摘要。
    # 回傳：字串（可直接交給 storage.save_output_file 上傳）
    try:
        # 步驟：邊界情況 — 空清單回傳空字串
        if not execution_log:
            return ""

        # 步驟：逐筆序列化為 JSON，每行一筆，以換行符分隔
        lines = []
        for record in execution_log:
            lines.append(json.dumps(record, ensure_ascii=False))

        # 回傳：以換行符連接所有行，結尾加換行符
        return "\n".join(lines) + "\n"
    except Exception:
        # 永不讓未處理例外逸出
        return ""


def classify_source_category(source):
    """根據 source 字串判斷該證據屬於哪個來源類別。

    回傳類別名稱字串（price / news / onchain / sentiment / macro / quant /
    derivatives / defi / prediction），若無法分類則回傳 None。
    此函式可供 export 驗證和其他模組共用。
    """
    _CATEGORY_KEYWORDS = {
        "price": ["binance", "coingecko", "klines", "ohlcv", "price", "orderbook", "depth"],
        "news": ["news", "rss", "github", "coindesk", "theblock", "cointelegraph"],
        "onchain": ["mempool", "etherscan", "blockscout", "helius", "xrpl", "onchain"],
        "sentiment": ["alternative.me", "fear", "greed", "sentiment"],
        "macro": ["fred", "macro", "stlouisfed"],
        "quant": ["quant", "indicator", "technical", "compute_quant"],
        "derivatives": ["hyperliquid", "deribit", "futures", "funding", "derivative"],
        "defi": ["llama", "defi", "tvl", "stablecoin"],
        "prediction": ["polymarket", "prediction", "gamma-api"],
    }
    source_lower = str(source).lower() if source else ""
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in source_lower for kw in keywords):
            return category
    return None


def validate_before_export(evidence_list, analysis_text, analyzed_evidence_ids=None):
    # 功能：交付前的自我檢查，把命題的評分觀察點寫成程式化驗證。
    # 檢查項目：
    #   1. 每筆證據的四個必填欄位是否齊備
    #   2. 資料來源類別數是否 >= 3（命題會看「來源類型是否多樣」）
    #   3. 是否有付費來源被當成唯一依據
    #   4. 報告中是否出現投資建議語句（買進／賣出／目標價）
    #   5. 孤兒 evidence_id 檢查（分析引用但不存在於 evidence_list 的 ID）
    # 回傳：(是否全數通過, 未通過項目的清單)
    #      未通過不阻止輸出，而是把警示寫進報告的限制段落。
    try:
        failures = []

        # 步驟 1：四欄位齊備檢查
        required_fields = ["source", "fetched_at", "content_reference", "related_claim"]
        for i, record in enumerate(evidence_list):
            missing = [f for f in required_fields if not record.get(f)]
            if missing:
                failures.append(f"證據 #{i+1} 缺少欄位：{', '.join(missing)}")

        # 步驟 2：來源類別數 >= 3（使用獨立的 classify_source_category）
        found_categories = set()
        for record in evidence_list:
            cat = classify_source_category(record.get("source", ""))
            if cat:
                found_categories.add(cat)
        if len(found_categories) < 3:
            failures.append(
                f"來源類別數不足：僅有 {len(found_categories)} 類（需 >= 3）"
            )

        # 步驟 3：付費來源非唯一依據
        # 付費來源關鍵字（需要 API Key 的服務）
        paid_keywords = ["coingecko", "cryptopanic", "etherscan", "helius", "fred"]
        # 免費來源關鍵字（不需要 API Key 的服務）
        free_keywords = [
            "binance", "mempool", "blockscout", "xrpl",
            "alternative.me", "quant", "indicator",
            "hyperliquid", "deribit", "polymarket", "llama",
        ]
        has_paid = False
        has_free = False
        for record in evidence_list:
            source_lower = str(record.get("source", "")).lower()
            if any(kw in source_lower for kw in paid_keywords):
                has_paid = True
            if any(kw in source_lower for kw in free_keywords):
                has_free = True
        if has_paid and not has_free:
            failures.append("付費來源為唯一依據：缺少免費公開來源佐證")

        # 步驟 4：無投資建議語句
        forbidden_phrases = [
            "買進", "賣出", "目標價", "建議持有",
            "建議買入", "建議賣出", "應該買", "應該賣",
        ]
        text_to_check = str(analysis_text) if analysis_text else ""
        found_phrases = [p for p in forbidden_phrases if p in text_to_check]
        if found_phrases:
            failures.append(
                f"報告含投資建議語句：{'、'.join(found_phrases)}"
            )

        # 步驟 5：孤兒 evidence_id 檢查
        if analyzed_evidence_ids:
            known_ids = {
                record.get("evidence_id") for record in evidence_list
                if record.get("evidence_id")
            }
            orphans = [eid for eid in analyzed_evidence_ids if eid not in known_ids]
            if orphans:
                failures.append(
                    f"孤兒 evidence_id（分析引用但不存在於證據清單）：{', '.join(orphans[:5])}"
                    + (f"…等共 {len(orphans)} 筆" if len(orphans) > 5 else "")
                )

        # 回傳：(全數通過, 未通過項目清單)
        all_passed = len(failures) == 0
        return (all_passed, failures)
    except Exception:
        # 永不讓未處理例外逸出；發生例外時視為未通過
        return (False, ["validate_before_export 執行時發生內部錯誤"])


# ─── C7 report_data Export ───────────────────────────────────────────────────

def export_report_data(report_data):
    """Serialize C7 report_data to JSON string for storage as report_data.json.

    Args:
        report_data: Validated C7 dict (from report.generate_report_data).

    Returns:
        JSON string or None if report_data is None/invalid.
    """
    try:
        if report_data is None:
            return None
        if not isinstance(report_data, dict):
            return None
        return json.dumps(report_data, ensure_ascii=False, indent=2)
    except Exception:
        return None
