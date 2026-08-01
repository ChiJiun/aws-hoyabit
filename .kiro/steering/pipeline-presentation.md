---
inclusion: always
---

# 資料管線與呈現規則

本文件將 `docs/pipeline-presentation-plan.md` 轉為開發時必須遵循的跨模組規則。欄位契約以 `.kiro/steering/contracts.md` 為準；模組驗收以各 `.kiro/specs/*` 為準。

## 1. 四層管線

1. **題型判別**：輸出 `single_integration | hypothesis | comparison`。兩個幣種固定為 `comparison`；單幣種以規則優先，語意不明時才由 LLM 兜底。結果必須寫入 execution log。
2. **蒐集層**：Phase A 依題型與幣種建立決定性預抓計畫並受限並行執行；Phase B 才由 Agent 根據 Phase A 摘要補洞。每次工具執行仍須遵循 C1/C2，成功與失敗都寫 execution log。
3. **處理層**：工具正規化與單源 `anomaly_flags` → Agent 跨源背離核對 → 事實／推論／結論 → 題型模板收斂。所有數值運算由工具或決定性程式完成，前端與 LLM 不自行計算。
4. **呈現層**：同一次分析同時產生 `report.md` 與 C7 `report_data.json`；前者供人閱讀，後者只供機器渲染。兩者的結論、信心、訊號與引用不得互相矛盾。

## 2. Phase A / Phase B 邊界

- Phase A 目標約 90 秒，採 bounded concurrency；單一來源 timeout、rate limit 或 schema error 不得取消其他工作。
- Phase A 的題型矩陣是**預抓能力計畫**，不是固定報告分母、Agent 工具配額或強迫引用清單。只有與題目相關且品質可用的結果才能進入推理；失敗結果只形成缺口與 execution log。
- Phase B 每輪前檢查總時間預算；剩餘預算低於 20% 時停止新增蒐集並強制收斂。
- `single_integration` 強調跨維度整合；`hypothesis` 必須區分支持／反對／中性；`comparison` 必須在相同維度比較並以程式計算相關係數與相對強弱。

## 3. C7 與 coverage 語意

- `report_data` 是視覺化唯一資料來源；Frontend 不得從 Markdown 抽取數字或重算指標。
- `coverage.pct` 僅表示「本題 Phase A 題目相關預抓能力中，品質可用結果的比例」：`got / (got + missing)`。它不是固定五維度分數、來源多樣性分數、報告品質分數或投資信心。
- `got` 與 `missing` 必須列出能力 ID；`missing` 必須附原因。若沒有題目相關預抓能力，`pct` 為 `null`，不得以 100 代替。
- `coverage.pct < 60` 只觸發資料可用性警示，不自動改寫模型結論；信心仍須依證據品質校準。

## 4. 呈現與降級

- Frontend 依 `question_type` 選用 single、hypothesis、comparison 三版面；圖表只讀 C7 `series`。
- 無資料維度必須明示原因，不可靜默隱藏；證據查證優先顯示人類可讀來源，API endpoint 留在 evidence JSON。
- `build_report_data`、C7 驗證或圖表渲染失敗時，必須記錄錯誤並 fallback 至純 `report_text`/marked 渲染，不能阻斷 Markdown、Evidence 與 Execution Log 交付。
- 所有版面維持資訊提煉定位，不輸出買賣、倉位或目標價建議。
