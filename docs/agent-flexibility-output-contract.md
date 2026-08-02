# Agent 彈性與穩定輸出設計

## 一、目的

本文件定義如何同時滿足兩項看似衝突的需求：

1. 面對競賽現場未知題目，Agent 能依問題動態拆題、選擇資料來源並處理矛盾訊號。
2. 無論 Agent 如何規劃，前端、分析報告、Evidence List 與 Execution Log 都維持可預期、可驗證的格式。

核心原則是：

> **內部探索有彈性，外部輸出有契約；模型負責判斷，程式負責格式與驗證。**

## 二、命題要求的解讀

命題文件不強制固定章節數量、長度或排版，Final Report 可採 Markdown、HTML 或 Dashboard；但以下內容不可缺少：

- 市場判斷。
- 關鍵依據，以及證據如何支撐判斷。
- 信心、已知限制、資料不足及可能推翻結論的條件。
- 每筆 Evidence 至少具備 `source`、`fetched_at`、`content_reference`、`related_claim`。
- Execution Log 記錄時間戳記、主要工具呼叫、資料取得及流程摘要。
- 核心判斷必須由自有 Agent 流程產生，不能直接提交第三方分析結論。
- 正式執行需在 15 分鐘內完成，且原則上只有一次正式執行機會。

因此，「未知題目」要求規劃層具備彈性，不代表報告資料結構也必須自由生成。

## 三、自由 Markdown 的風險

如果 System Prompt 同時要求模型決定資料蒐集、推理與排版，可能發生：

- 標題名稱或順序改變，前端解析失敗。
- JSON、Markdown 或表格混合，欄位無法穩定擷取。
- evidence ID 被縮短、改寫或杜撰，報告與 Evidence List 無法對應。
- 子 Agent 使用不同單位、時間窗或信心尺度，結果無法比較。
- 模型輸出「配置、進出場」等接近投資建議的文字。
- 某次輸出缺少限制或矛盾訊號，卻仍被當成完整報告。
- 前端為固定維度設計，遇到題目驅動的新維度時版面失真。

目前程式雖已由 `report.py` 固定渲染三個必要章節，但 `summarize_final_analysis()` 仍先要求模型產生 Markdown，再由正規表示式拆章；這只能降低版面漂移，無法消除語意與引用格式漂移。

## 四、目標工作流

```text
使用者輸入：幣種 + 未知題目
              │
              ▼
      1. Planner（動態拆題）
              │ AnalysisPlan
              ▼
      2. 受控研究執行器
       ├─ 市場結構研究
       ├─ 事件／新聞研究
       ├─ 鏈上／基本面研究
       └─ 總經研究
              │ ResearchResult[]
              ▼
      3. Evidence Validator
              │ ValidatedResearch
              ▼
      4. Synthesis Agent
              │ ReportModel
              ▼
      5. 決定性 Renderer
       ├─ Markdown 報告
       ├─ Dashboard API response
       ├─ Evidence List
       └─ Execution Log
```

### 4.1 Planner：允許彈性的地方

Planner 可依題目動態決定：

- 題型與時間範圍。
- 需要驗證的子問題。
- 與題目相關的分析維度。
- 使用哪些工具及其優先順序。
- 哪些資料需要交叉驗證。
- 總工具數、輪數、時間與 token 預算。

Planner 不得決定最終畫面或自行增加任意輸出欄位。

建議固定輸出：

```json
{
  "question_type": "hypothesis_validation",
  "time_horizon": "1d-14d",
  "subquestions": [],
  "selected_dimensions": [],
  "tool_requests": [],
  "time_budget_seconds": 600
}
```

### 4.2 Sub-agent：使用共同研究契約

Sub-agent 應是可選的專業研究角色，不是每次全部啟用。Planner 僅選擇與題目相關的 2～3 個角色，避免延遲、成本與脈絡膨脹。

每個 Sub-agent 只能回傳共同的 `ResearchResult`，不得直接撰寫最終 Markdown：

```json
{
  "dimension": "derivatives",
  "summary": "槓桿部位上升，但價格尚未突破區間",
  "facts": [
    {
      "statement": "未平倉量近七日增加",
      "evidence_ids": ["完整-evidence-uuid"]
    }
  ],
  "signals": [],
  "contradictions": [],
  "limitations": []
}
```

所有 Sub-agent 共用同一 Evidence Store；`source`、`fetched_at` 與 `content_reference` 仍由程式和工具建立，不由模型自由填寫。

### 4.3 Validator：在模型與畫面之間設硬性關卡

Validator 至少檢查：

- JSON Schema 是否通過。
- evidence ID 是否完整、存在且沒有重複。
- 每項事實是否至少引用一筆有效證據。
- 關鍵結論是否具備跨來源或跨維度支持。
- 來源時間是否符合題目時間範圍。
- 比較資料的單位、粒度與時間窗是否相容。
- 技術數值是否由決定性工具計算，而非模型心算。
- 是否清楚記錄矛盾、缺口和失敗工具。
- 是否含直接或變相的投資建議。

驗證失敗時只允許一次受控修正；仍失敗則使用保守的 fallback 報告，明確標示證據不足，不把無效格式送到前端。

### 4.4 Synthesis Agent：只產生 ReportModel

建議最終中間格式：

```json
{
  "market_state": {
    "regime": "低波動、槓桿堆積",
    "confidence": "medium",
    "time_horizon": "1d-14d"
  },
  "key_findings": [],
  "supporting_signals": [],
  "contradicting_signals": [],
  "catalysts": [],
  "risks": [],
  "invalidation_conditions": [],
  "watch_items": [],
  "limitations": [],
  "evidence_ids": []
}
```

`confidence` 使用有限列舉值，例如 `low`、`medium`、`high`，不可由不同 Agent 自創百分比分數。

### 4.5 Renderer：由程式保證最終格式

Python Renderer 負責：

- 固定必要章節與顯示順序。
- 將完整 evidence ID 轉成可點擊引用。
- 對文字做 HTML escaping 與 Markdown 安全處理。
- 無資料時顯示一致的空狀態。
- 依 `ReportModel` 渲染 Markdown 與前端卡片。
- 產生合法 JSON Evidence List 與 JSONL Execution Log。

前端只依賴 `ReportModel`／API contract，不解析模型任意文字來推測欄位。

## 五、時間與失敗控制

建議 15 分鐘上限的內部預算：

| 階段 | 建議上限 |
|---|---:|
| Planner | 30–45 秒 |
| 資料工具與 Sub-agent | 7–9 分鐘 |
| 交叉驗證與整合 | 2–3 分鐘 |
| Validator 與一次修正 | 1–2 分鐘 |
| Renderer、上傳與緩衝 | 1–2 分鐘 |

另需設定：

- 全流程 deadline，而非只限制單次 Agent 輪數。
- 每個工具 timeout、有限重試與錯誤分類。
- 最多同時啟用 2～3 個 Sub-agent。
- Bedrock throttling、模型 timeout 及部分工具失敗的降級策略。
- 即使流程提前停止，也要輸出已取得證據、Execution Log 與限制說明。

## 六、AWS 部署影響

競賽版可維持單一 Lambda：

- Sub-agent 是同一 Lambda 內的多個 Bedrock 對話，不代表需要多個 AWS Agent 或 Lambda。
- S3、Function URL、IAM Role 與前端 bucket 不需因工作流重構而重建。
- 若仍使用相同 Bedrock 模型，主要 IAM 權限不變。
- 可能需調整 Lambda timeout、memory、`MAX_AGENT_TURNS`、總時間預算與模型呼叫額度。
- 新增資料來源時才需要加入 API key、環境變數或 IAM 權限。

只有在後續需要長時間平行任務、可恢復狀態或獨立重試時，才考慮 Step Functions、多 Lambda 或佇列；競賽階段優先維持部署簡單與可重現。

## 七、目前實作的前置修復

在重構前必須先恢復可執行基線。目前工作區曾檢查到 `agent.py`、`report.py`、`test_report.py` 及部分 spec 文件存在未解決的 Git 合併衝突，Python 編譯會因此失敗。處理順序應為：

1. 指定單一整合者解決衝突。
2. 執行 `python -m py_compile`。
3. 執行 Agent、Report 與 Handler 的目標測試。
4. 保存一份可運行基線後，再開始 Schema 與 Sub-agent 重構。
5. 不在未解決衝突的檔案上平行開發。

## 八、驗收標準

- 同一份 `ReportModel` 可穩定渲染 Markdown 與 Dashboard。
- 任意題型都不會改變 API 頂層欄位。
- 報告引用的每個 evidence ID 都能在 Evidence List 找到完整記錄。
- 模型漏章節或輸出無效 JSON 時，系統會修正或降級，不會產生破版。
- 不相關的工具不會為了固定配額而被強制呼叫。
- 部分工具失敗時仍能在期限內產出保守報告及完整日誌。
- 報告能清楚區分事實、推論、結論、矛盾、限制及推翻條件。
- 不輸出買進、賣出、配置比例、目標價或其他投資建議。
