# Specs 導覽與分工

`crypto-market-agent/` 為**主 spec**:21 條需求(R1–R21)的唯一編號來源與整體驗收依據,勿刪勿改編號。
以下 6 個子 spec 按模組切分,邊界與契約見 `steering/structure.md`、`steering/contracts.md`,可平行開發。

| 子 spec | 負責檔案 | 對應主 spec 需求 | 對應主 tasks | 建議人力 |
|---|---|---|---|---|
| core-infrastructure | config / evidence / storage | R2.6, R4, R5, R18, R19 | 1.x, 12.x | 1 人,**最先完成** |
| market-data-tools | tools/price, tools/quant | R6, R11, R20 | 2.x, 3.x | 1 人 |
| intel-data-tools | tools/news, onchain, sentiment, macro | R7–R10, R20 | 4.x–7.x | 1–2 人 |
| agent-orchestrator | agent / handler / 整合測試 | R1, R2, R3, R14, R16, R21 | 9.x, 14.x, 16.x | 1 人 |
| report-delivery | report / export | R12, R13, R15 | 10.x, 11.x | 1 人 |
| frontend-ui | frontend/index.html | R17 | 15.x | 1 人 |

## 開發順序與解耦要點
1. Wave 0:core-infrastructure 先定案(其他人可先用它的介面 stub 開工)
2. Wave 1(平行):market-data-tools、intel-data-tools、report-delivery、frontend-ui
   - tools 開發者:只需遵守契約 C1/C2/C3,可用假資料單獨測試自己的工具
   - report 開發者:只消費 evidence_list + 分析文字,可用假 evidence 開發
   - frontend 開發者:只認契約 C5,可先 mock API 回應
3. Wave 2:agent-orchestrator 整合(依賴各工具就緒)
4. Wave 3:整合測試(5 幣種 × 3 題型)、部署、演練 15 分鐘時限


## Pipeline Presentation 增補

`docs/pipeline-presentation-plan.md` 的落地規則由 `steering/pipeline-presentation.md` 與契約 C7 統一管理，不建立另一套重複主需求編號。各模組責任如下：

| 模組 | Pipeline 新責任 |
|---|---|
| agent-orchestrator | 題型判別、Phase A bounded parallel prefetch、Phase B 補洞與 <20% 收斂 |
| report-delivery | `build_report_data()`、題型 Markdown 模板、C7/Markdown 一致性與安全降級 |
| frontend-ui | 三題型版面、Chart.js、查證摺疊、低資料可用率與無資料狀態 |
| core-infrastructure | C7 schema 常數與純函式驗證器 |
| market-data-tools | 近 90 日價格與 comparison 相對強弱序列 |
| intel-data-tools | 資金費率、供給與事件序列的可選輸出 |

建議順序：C7 schema → 工具 series → Agent Phase A/B → Report C7 → Frontend 三版面 → 三題型 E2E 與降級演練。所有增補沿用 R1–R21，不改既有需求編號。
