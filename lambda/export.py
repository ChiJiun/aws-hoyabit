"""
export.py — 交付物匯出

把執行期間累積的證據與日誌，轉成命題要求的檔案格式。
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
            # JSON 格式輸出：每筆保留五個欄位供追溯
            exported = []
            for record in evidence_list:
                exported.append({
                    "evidence_id": record.get("evidence_id", ""),
                    "source": record.get("source", ""),
                    "fetched_at": record.get("fetched_at", ""),
                    "content_reference": record.get("content_reference", {}),
                    "related_claim": record.get("related_claim", ""),
                })
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


def validate_before_export(evidence_list, analysis_text):
    # 功能：交付前的自我檢查，把命題的評分觀察點寫成程式化驗證。
    # 檢查項目：
    #   1. 每筆證據的四個必填欄位是否齊備
    #   2. 資料來源類別數是否 >= 3（命題會看「來源類型是否多樣」）
    #   3. 是否有付費來源被當成唯一依據
    #   4. 報告中是否出現投資建議語句（買進／賣出／目標價）
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

        # 步驟 2：來源類別數 >= 3
        # 根據 source 欄位的 URL 或工具名稱判斷類別
        category_keywords = {
            "price": ["binance", "coingecko", "klines", "ohlcv", "price"],
            "news": ["cryptopanic", "news", "rss", "github"],
            "onchain": ["mempool", "etherscan", "blockscout", "helius", "xrpl", "onchain"],
            "sentiment": ["alternative.me", "fear", "greed", "sentiment"],
            "macro": ["fred", "macro", "stlouisfed"],
            "quant": ["quant", "indicator", "technical"],
        }
        found_categories = set()
        for record in evidence_list:
            source_lower = str(record.get("source", "")).lower()
            for category, keywords in category_keywords.items():
                if any(kw in source_lower for kw in keywords):
                    found_categories.add(category)
                    break
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

        # 回傳：(全數通過, 未通過項目清單)
        all_passed = len(failures) == 0
        return (all_passed, failures)
    except Exception:
        # 永不讓未處理例外逸出；發生例外時視為未通過
        return (False, ["validate_before_export 執行時發生內部錯誤"])