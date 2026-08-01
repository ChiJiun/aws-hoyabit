# frontend-ui 設計

## 定位
評審看到的第一印象(Demo 錄影主畫面)。單檔 HTML + vanilla JS + marked.js(CDN),依賴僅契約 C5。

## 元件
- 幣種選擇:五顆按鈕,aria-pressed 切換,上限 2 顆(第 3 顆點擊時提示比較題僅支援兩幣)
- 題目輸入:textarea + 三題型範例快速填入按鈕(Demo 時省打字時間)
- 執行中:經過秒數計時器 + 進度文字輪播(「正在蒐集鏈上資料…」等,與後端實際階段無關但降低等待焦慮);>600 秒顯示偏長提示
- 結果區:marked.parse 渲染報告;evidence/log 下載按鈕(presigned URL);run_id 顯示
- 錯誤區:顯示後端 error 欄位原文 + 建議動作,絕不顯示通用「發生錯誤」

## JS 函式(對應主 spec tasks 15.x)
initCoinSelector / showLoading / showError / callAnalysisApi / renderReport / handleSubmit;API_URL 常數置頂,部署後替換

## 開發方式(解耦)
本機以 `python -m http.server` + mock 回應 JSON 開發;整合日只需替換 API_URL
