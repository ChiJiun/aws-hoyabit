# frontend-ui 需求

範圍:frontend/index.html(單檔)。編號引用主 spec。

## 承接的主 spec 需求
- **R17 前端介面**(全部):幣種按鈕(1–2 個)、題目輸入、前端驗證、執行中狀態(經過時間 + 進度文字輪播)、marked.js 渲染、下載連結、S3 靜態託管

## 本模組補充驗收條件
1. THE Frontend SHALL 只依賴契約 C5 的請求/回應格式,可用本機 mock server 完整開發測試
2. WHEN 等待超過 10 分鐘仍無回應,THE Frontend SHALL 顯示「執行時間偏長」提示但不中斷等待(Lambda 上限 15 分)
3. THE Frontend SHALL 為 Live Demo 優化:清楚呈現執行過程與輸出(決賽需錄影,畫面即評分素材)
