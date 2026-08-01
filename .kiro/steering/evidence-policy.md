---
inclusion: fileMatch
fileMatchPattern: "lambda/{tools/*.py,evidence.py,export.py,report.py,agent.py}"
---

# 證據與品質政策(編輯資料工具/證據/報告相關程式時必讀)

## 證據四欄位(命題硬性要求,抽查項目)
每筆證據必含:source(來源名稱或 URL)、fetched_at(UTC ISO 8601)、content_reference(引用片段/查詢參數/指標數值/資料區間)、related_claim(對應的報告判斷)。
- 網頁/新聞/公告 → source 用 URL + 引用片段
- API/CSV/鏈上/Dashboard → content_reference 需含 endpoint、查詢參數、時間範圍等可回溯資訊
- 原始回應一律封存 runs/{run_id}/raw/{evidence_id}.json

## 品質紅線(export 前 validate_before_export 必檢)
1. 報告不得出現投資建議語句:買進、賣出、加倉、目標價、建議持有、進場、出場等
2. 證據來源類別 ≥ 3(價格/鏈上/新聞/情緒/總經)
3. 付費來源不得為某結論的唯一依據
4. 報告中每條關鍵依據必須引用存在的 evidence_id(不可有孤兒結論)
5. 同一來源家族的重複報導須標註,不得偽裝成多源共識

## 推理紀律(寫 system prompt 或報告模板時)
- 事實(有 evidence_id)→ 推論(說明邏輯)→ 結論(標信心程度)三層分離
- 訊號矛盾:明寫矛盾內容與取捨依據;資料缺失:列入信心說明的已知限制
- 數字一律由 compute_quant 決定性計算,禁止模型心算
