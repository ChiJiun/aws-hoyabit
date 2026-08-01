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
