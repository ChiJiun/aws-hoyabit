# report-delivery 設計

## 定位
「結構由程式保證,不依賴模型自律」(R14 精神)。全模組無外部 API 呼叫,輸入只有 analysis_text + evidence_list + execution_log,**可用假資料完全獨立開發**。

## report.py
- `calculate_coverage(evidence_list) -> (pct, got: list, missing: list)`:五類別(價格/鏈上/新聞/情緒/總經)
- `build_evidence_table(evidence_list) -> str`:Markdown 表(evidence_id/來源/時間/對應判斷)
- `render_report(analysis_text, evidence_list, missing_sources, coverage) -> str`:f-string 模板,三章節(## 市場判斷 / ## 關鍵依據 / ## 信心說明)必然存在;附錄含覆蓋率 + 證據表;missing_sources 自動寫入信心說明

## export.py
- `export_evidence_list(evidence_list, fmt="json")`:JSON(主)/CSV(選)
- `export_execution_log(log) -> str`:JSONL,每行可 json.loads
- `validate_before_export(report_text, evidence_list) -> (bool, failures: list[str])` 檢查:
  1. 禁語清單(買進/賣出/加倉/減倉/目標價/建議持有/進場/出場…,含英文 buy/sell/take profit)
  2. 來源類別 ≥ 3
  3. 四欄位齊備率 100%
  4. 報告中引用的 evidence_id 全部存在(無孤兒引用)
  5. 付費來源非唯一依據
- 驗證失敗:仍匯出,但報告頂部插入 `> ⚠ 品質警示:` 區塊列出未通過項(降級而非失敗)

## 測試重點
P16 三章節必存在|P17 禁語偵測|P18 覆蓋率計算|P11 JSONL 可解析|孤兒引用偵測
