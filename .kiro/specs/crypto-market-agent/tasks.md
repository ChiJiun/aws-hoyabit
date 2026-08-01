# 實作計畫：加密市場分析 AI Agent

## 概覽

依據設計文件中的架構，按照模組相依性由底層向上逐步實作。優先完成基礎設施模組（config、evidence），再實作六個獨立的資料工具，接著實作核心 Agent 迴圈與報告層，最後整合進入點與前端。

## 任務清單

- [x] 1. 基礎設施模組（config.py、evidence.py）

  - [x] 1.1 實作 config.py 的 load_local_env 函式
    - 使用 python-dotenv 的 load_dotenv() 從專案根目錄的 .env 載入環境變數
    - 確保所有環境變數（AWS_REGION、BEDROCK_MODEL_ID、DATA_BUCKET、API 金鑰等）已正確讀取
    - _需求：19.1、19.2_

  - [x] 1.2 實作 evidence.py 的 reset_stores 函式
    - 清空全域 evidence_list 與 execution_log 列表
    - 確保 Lambda 容器重複使用時不會殘留前次資料
    - _需求：2.6_ | _Property 4: 容器重複使用不汙染_

  - [x] 1.3 實作 evidence.py 的 log_evidence 函式
    - 驗證 related_claim 非空且長度足夠，不足則回傳錯誤不寫入
    - 自動產生 evidence_id（UUID）、source（從 fetch_result 取）、fetched_at（ISO 8601 UTC）、content_reference
    - 呼叫 storage.save_raw_payload() 封存原始回應
    - 回傳 evidence_id 字串
    - _需求：4.1、4.2、4.3、4.4、4.5、4.6_ | _Property 7、8、9_

  - [x] 1.4 實作 evidence.py 的 log_execution_step 函式
    - 記錄含 timestamp、tool_name、status、elapsed_ms、evidence_id、note 的執行紀錄
    - 成功與失敗的呼叫都必須記錄
    - _需求：5.1、5.2_ | _Property 10_

  - [x] 1.5 撰寫 evidence.py 的屬性測試
    - **Property 4: 容器重複使用不汙染** — reset_stores 後 evidence_list 與 execution_log 為空
    - **Property 7: 證據記錄欄位完整性** — log_evidence 產生的記錄包含正確五欄位
    - **Property 8: 空 related_claim 被拒絕** — 空白 related_claim 不增加 evidence_list 長度
    - **Property 9: Evidence ID 唯一性** — 同次執行中所有 evidence_id 互不相同
    - **Property 10: 執行紀錄完整性** — log_execution_step 新增一筆包含必要欄位的記錄
    - **驗證: 需求 2.6、4.1、4.2、4.4、4.5、5.1、5.2**

- [x] 2. 技術指標計算工具（tools/quant.py）

  - [x] 2.1 實作 calc_atr_pct 函式
    - 計算 ATR（平均真實區間）並轉為佔收盤價的百分比
    - 輸入：pandas DataFrame（含 high、low、close 欄位）、window 期間
    - _需求：11.1、11.2_ | _Property 14_

  - [x] 2.2 實作 calc_bollinger_bandwidth 函式
    - 計算布林帶寬（上下軌距離佔中軌的比例）
    - 輸入：pandas DataFrame、window 期間
    - _需求：11.1、11.2_

  - [x] 2.3 實作 calc_adx 函式
    - 計算 ADX（平均趨向指標），衡量趨勢強度
    - 輸入：pandas DataFrame（含 high、low、close 欄位）、window 期間
    - _需求：11.1、11.2_

  - [x] 2.4 實作 calc_percentile_rank 函式
    - 計算當前數值在過去 lookback 天資料中的百分位排名（0-100）
    - 此函式為所有指標共用的「絕對值→相對位置」轉換
    - _需求：11.3_ | _Property 14_

  - [x] 2.5 實作 calc_correlation 函式
    - 計算兩個幣種日報酬率的 Pearson 相關係數
    - 結果必定在 [-1, 1] 區間內
    - _需求：11.4_ | _Property 15_

  - [x] 2.6 實作 compute_quant 主函式
    - 依 features 清單（atr_pct、bollinger_bandwidth、adx、volume_zscore、realized_vol、correlation）逐一計算
    - 每個指標同時附帶百分位排名
    - 當 compare_symbol 不為 None 時計算相關係數
    - 回傳統一格式 dict（raw、source、content_reference、summary）
    - 失敗時回傳 error dict 而非拋出例外
    - _需求：11.1、11.2、11.3、11.4、11.5、20.1、20.2、20.3_ | _Property 12、13、14_

  - [x] 2.7 撰寫 quant.py 的屬性測試
    - **Property 14: 技術指標含百分位** — 每個指標結果包含原始數值與 0-100 百分位
    - **Property 15: 相關係數值域** — calc_correlation 結果必在 [-1, 1] 區間
    - **Property 12: 工具永不拋錯** — 任何輸入下 compute_quant 回傳 dict 而非拋例外
    - **驗證: 需求 11.3、11.4、20.2**

- [x] 3. 價格與 OHLCV 資料工具（tools/price.py）

  - [x] 3.1 實作 fetch_recent_from_exchange 函式
    - 從 Binance 公開 API 取得 BASELINE_END_DATE 之後的日線 OHLCV
    - 使用與基準資料相同的交易對（{symbol}USDT）
    - 回傳 pandas DataFrame，欄位與基準 CSV 一致
    - _需求：6.3_

  - [x] 3.2 實作 check_data_seam 函式
    - 比對基準資料與即時資料的重疊日期收盤價差異百分比
    - 回傳 (是否通過、重疊日數、最大價差百分比)
    - 結果記入 execution_log
    - _需求：6.4_

  - [x] 3.3 實作 get_price_ohlcv 主函式
    - 讀取 S3 基準 CSV → 判斷是否需補即時資料 → 拼接 → 篩選日期範圍
    - 以 CoinGecko 作為備用來源
    - 回傳統一格式 dict；失敗時回傳 error dict
    - _需求：6.1、6.2、6.3、6.4、6.5、6.6、20.1、20.2、20.3_ | _Property 12、13_

  - [x] 3.4 撰寫 price.py 的單元測試
    - 測試基準 CSV 讀取與日期篩選
    - 測試 check_data_seam 在價差過大時的警告
    - 測試 API 失敗時回傳 error dict
    - **Property 12: 工具永不拋錯**
    - **驗證: 需求 6.1、6.6**

- [x] 4. 新聞與官方公告工具（tools/news.py）

  - [x] 4.1 實作 fetch_official_announcements 函式
    - 從各專案官方部落格 RSS 與 GitHub releases API 取得一手公告
    - 依幣種分派到正確的來源（BTC→bitcoin.org、ETH→blog.ethereum.org 等）
    - _需求：7.2_

  - [x] 4.2 實作 search_news 主函式
    - 呼叫 Google News RSS(關鍵字含幣種)與媒體 RSS 白名單取得幣種新聞
    - 合併 fetch_official_announcements 結果
    - 標註同一來源家族的重複報導
    - 回傳統一格式 dict；失敗時回傳 error dict
    - _需求：7.1、7.2、7.3、7.4、7.5、20.1、20.2、20.3_ | _Property 12、13_

  - [x] 4.3 撰寫 news.py 的單元測試
    - Mock RSS 回應，驗證結果解析
    - 測試 API 失敗時回傳 error dict
    - **Property 12: 工具永不拋錯**
    - **驗證: 需求 7.1、7.5**

- [x] 5. 鏈上資料工具（tools/onchain.py）

  - [x] 5.1 實作 fetch_btc_onchain 函式
    - 從 mempool.space 取得 BTC 鏈上資料（免金鑰）
    - 支援 active_addresses、tx_count 等指標
    - _需求：8.1_

  - [x] 5.2 實作 fetch_evm_onchain 函式
    - ETH → Etherscan API V2（需金鑰）；BNB → Blockscout（免金鑰）
    - 兩者共用同一套解析邏輯（API 格式相容）
    - _需求：8.2、8.3_

  - [x] 5.3 實作 fetch_sol_onchain 函式
    - 從 Helius 取得 Solana 鏈上資料（需金鑰）
    - _需求：8.4_

  - [x] 5.4 實作 fetch_xrp_onchain 函式
    - 從 XRPL 公開節點取得 XRP 帳本資料（標準 JSON-RPC，免金鑰）
    - _需求：8.5_

  - [x] 5.5 實作 get_onchain 主函式
    - 依 symbol 分派到對應的 fetch 函式（match/case）
    - content_reference 包含 API endpoint、查詢參數、資料時間範圍
    - 回傳統一格式 dict；失敗時回傳 error dict
    - _需求：8.1、8.2、8.3、8.4、8.5、8.6、8.7、20.1、20.2、20.3_ | _Property 12、13_

  - [x] 5.6 撰寫 onchain.py 的單元測試
    - Mock 各鏈 API 回應，驗證幣種分派正確性
    - 測試所有 5 條鏈的 API 失敗時回傳 error dict
    - **Property 5: 工具分派正確性**
    - **Property 12: 工具永不拋錯**
    - **驗證: 需求 8.1–8.7**

- [x] 6. 市場情緒工具（tools/sentiment.py）

  - [x] 6.1 實作 get_sentiment 函式
    - 呼叫 alternative.me Fear & Greed Index API
    - 取得當前指數值與近 lookback_days 天的走勢
    - content_reference 包含 API endpoint、查詢時間範圍、指數數值與分級文字
    - 回傳統一格式 dict；失敗時回傳 error dict
    - _需求：9.1、9.2、9.3、20.1、20.2、20.3_ | _Property 12、13_

  - [x] 6.2 撰寫 sentiment.py 的單元測試
    - Mock API 回應，驗證 content_reference 包含完整資訊
    - 測試 API 失敗時回傳 error dict
    - **Property 12: 工具永不拋錯**
    - **驗證: 需求 9.1、9.3**

- [x] 7. 總體經濟工具（tools/macro.py）

  - [x] 7.1 實作 fetch_upcoming_events 函式
    - 取得未來已排定的重要總經事件（FOMC、CPI 公布日等）
    - _需求：10.1_

  - [x] 7.2 實作 get_macro 主函式
    - 呼叫 FRED API 取得指定總經指標（DXY、10Y 殖利率、聯邦基金利率）
    - 整合 fetch_upcoming_events 結果
    - content_reference 包含 FRED series ID、查詢時間範圍、數值序列摘要
    - 回傳統一格式 dict；失敗時回傳 error dict
    - _需求：10.1、10.2、10.3、10.4、20.1、20.2、20.3_ | _Property 12、13_

  - [ ]* 7.3 撰寫 macro.py 的單元測試
    - Mock FRED API 回應，驗證 content_reference 包含 series ID
    - 測試 API 失敗時回傳 error dict
    - **Property 12: 工具永不拋錯**
    - **驗證: 需求 10.1、10.4**

- [ ] 8. 檢查點 — 基礎設施與工具模組
  - 確認所有測試通過，如有疑問請詢問使用者。

- [ ] 9. Agent 主迴圈（agent.py）

  - [x] 9.1 實作 build_tool_config 函式
    - 組出 Bedrock Converse API 的 toolConfig JSON
    - 每個 toolSpec 的 inputSchema 必須將 related_claim 列為 required
    - 包含六個工具的完整描述與參數定義
    - _需求：3.1、4.3_ | _Property 5_

  - [x] 9.2 實作 call_bedrock 函式
    - 呼叫 boto3 bedrock-runtime.converse()
    - 傳入 system=[{"text": SYSTEM_PROMPT}]、messages、toolConfig
    - 處理 ThrottlingException（等待 2 秒重試一次）、ModelTimeoutException、ValidationException
    - _需求：3.1_

  - [x] 9.3 實作 dispatch_tool_call 函式
    - 從 tool_use_block 解析 name 與 input
    - 透過 TOOL_DISPATCH 分派至對應函式並計時
    - 呼叫 log_evidence() 與 log_execution_step()
    - 回傳 toolResult（僅含 summary + evidence_id，不含 raw）
    - _需求：3.2、3.6、4.1、4.2、5.1、5.2_ | _Property 5、6_

  - [x] 9.4 實作 run_agent_loop 函式
    - 組裝初始 user 訊息，進入迴圈（最多 MAX_AGENT_TURNS 輪）
    - 每輪開始前檢查時間預算
    - stopReason 為 tool_use 時分派工具；為 end_turn 時跳出
    - 超時則強制跳出並標記
    - _需求：2.1、2.2、2.3、2.4、3.2、3.3_ | _Property 3_

  - [x] 9.5 實作 summarize_final_analysis 函式
    - 第二次 Bedrock 呼叫（不含 toolConfig）
    - 要求模型以「市場判斷／關鍵依據／信心說明」結構輸出
    - _需求：14.1_

  - [x]* 9.6 撰寫 agent.py 的單元測試
    - Mock Bedrock API，測試 end_turn 正確退出迴圈
    - 測試 MAX_AGENT_TURNS 達到上限時強制退出
    - 測試 dispatch_tool_call 的 toolResult 不含 raw 欄位
    - **Property 3: Agent Loop 必定終止**
    - **Property 5: 工具分派正確性**
    - **Property 6: Context 膨脹防護**
    - **驗證: 需求 2.1、2.3、3.2、3.6**

  - [x] 9.7 修訂 SYSTEM_PROMPT 的動態多維度分析規劃
    - 要求依題目選擇至少 2 個能回答不同子問題、彼此互補的相關維度，並交叉說明實際維度的一致訊號、背離訊號或證據不足
    - 移除固定五類、七工具或其他工具數量配額，以及強制工具呼叫順序；保留至少 3 個來源類別只作為匯出驗證政策
    - 要求只說明與題目相關或已嘗試的省略、失敗維度及其信心影響，不臆測無關缺口
    - _需求：12.2、13.2、13.3、13.4、13.5、13.6、13.9_

  - [x]* 9.8 更新 SYSTEM_PROMPT 單元測試
    - 驗證提示詞包含題目相關的互補維度選擇、跨維度一致／背離／不足比較及 evidence_id 要求
    - 驗證提示詞不含固定 5 類、7 工具配額或 mandatory tool order
    - _需求：12.2、12.3、12.9、13.2、13.3、13.4、13.5、13.6、13.9_

- [ ] 10. 報告渲染（report.py）

  - [x] 10.1 以決定性 13 維分類與多維度摘要取代 calculate_coverage
    - 移除固定五類覆蓋率計算，定義 13 個 ANALYSIS_DIMENSIONS，並依 capability_id、結構化 content_reference、canonical source provider 與工具預設值的固定優先序，為每筆已採用證據選出唯一 primary dimension
    - 實作 build_analysis_summary，從 evidence_list 與 execution-log-derived report metadata 彙整不重複證據筆數、canonical provider 獨立來源數、實際分析維度、逐維度 evidence/source/content_reference 明細、可確定的失敗嘗試與相關省略
    - 同一 provider 的不同 URL endpoint 只計為一個來源；只將 analyzed_evidence_ids 對應的證據列為實際分析，未知失敗維度不得臆測
    - 維持 C2 Evidence Record 與既有 C4 render_report 參數契約，report.py 不呼叫外部 API
    - _需求：12.5、12.6、12.7、13.5、13.6、13.9_ | _Property 17、18_

  - [x] 10.2 實作 build_evidence_table 函式
    - 將 evidence_list 轉為 Markdown 表格（evidence_id、來源、取得時間、對應判斷）
    - _需求：12.3_

  - [x] 10.3 更新 render_report 的多維度附錄與信心說明
    - 保留市場判斷、關鍵依據、信心說明三章節與完整證據表，並在附錄渲染實際分析維度、證據筆數、獨立來源數及逐維度明細
    - 渲染 error、unavailable、timeout 等已知失敗嘗試，並將題目相關省略／失敗的原因與信心影響寫入信心說明
    - 不輸出 x/5、固定五類分母、固定覆蓋百分比、x/3 匯出門檻達成率或維度分數
    - 僅消費 analysis_text、evidence_list、missing_sources 與既有 coverage 位置傳入的 report metadata，不新增 API 呼叫或跨模組依賴
    - _需求：12.1、12.3、12.4、12.5、12.6、12.7、12.8、12.9、13.2、13.3、13.4、13.5、13.6、13.9_ | _Property 18_

  - [x]* 10.4 更新 report.py 的屬性與單元測試
    - **Property 17: 維度分類決定性與完備性** — 涵蓋 13 維 capability、重複輸入、複合命中與固定優先序，結果必為唯一合法維度
    - **Property 18: 多維度附錄忠實且無固定分母** — 涵蓋重複 evidence_id、未採用證據、同 provider 不同 endpoint、URL hostname／非 URL provider canonicalization、成功失敗混合與相關／無關省略
    - 驗證附錄包含實際維度、證據筆數、獨立來源數、逐維度明細與 error／unavailable／timeout 失敗嘗試
    - 驗證輸出不含 x/5、固定覆蓋百分比、x/3 門檻達成率或 dimension score，且在模擬網路 client 失敗時仍可純本地完成渲染
    - **驗證: 需求 12.5、12.6、12.7、13.5、13.6、13.9**

- [x] 11. 交付物匯出（export.py）

  - [x] 11.1 實作 export_evidence_list 函式
    - 支援 JSON 與 CSV 兩種輸出格式
    - 每筆含 source、fetched_at、content_reference、related_claim
    - _需求：15.1_

  - [x] 11.2 實作 export_execution_log 函式
    - 輸出 JSONL 格式（每行一筆 JSON 物件）
    - _需求：5.3、15.1_ | _Property 11_

  - [x] 11.3 實作 validate_before_export 函式
    - 檢查 Evidence Record 完整、來源類別數 >= 3、付費來源非唯一，以及分析文字不含投資建議語句
    - 將三來源類別門檻只作為匯出 pass/fail 條件，不提供報告分母、覆蓋率或分數
    - 回傳 (全數通過, 未通過項目清單)
    - _需求：13.1、13.7、13.8、13.9_ | _Property 19、20_

  - [ ]* 11.4 更新 export.py 的屬性測試
    - **Property 19: 投資建議交付前必拒絕** — 任意包含禁止投資建議語句的分析文字都被標記未通過
    - **Property 20: 三來源類別門檻僅約束匯出** — 來源類別去重後只有 >= 3 才通過，且相同輸入不會使報告產生固定分母、百分比或分數
    - 將 export 的來源類別生成與 report 的 canonical source/provider 計數分開，避免混用兩種概念
    - **驗證: 需求 13.1、13.7、13.8、13.9**

- [x] 12. S3 讀寫模組（storage.py）

  - [x] 12.1 實作 read_baseline_csv 函式
    - 從 S3 路徑 baseline/{symbol}USDT_daily_ohlcv.csv 讀取並回傳 DataFrame
    - 本機測試時從本地 data/baseline/ 讀取
    - _需求：18.1_

  - [x] 12.2 實作 save_raw_payload 函式
    - 上傳原始 API 回應至 S3 路徑 runs/{run_id}/raw/{evidence_id}.json
    - 本機測試時寫入 outputs/ 資料夾
    - _需求：4.6、18.2_

  - [x] 12.3 實作 save_output_file 函式
    - 上傳交付物至 S3 路徑 runs/{run_id}/{filename}
    - _需求：15.2、18.2_

  - [x] 12.4 實作 generate_download_link 函式
    - 產生 S3 presigned URL，預設 1 小時有效
    - _需求：15.3、18.3、18.4_

- [ ] 13. 檢查點 — Agent 迴圈與報告模組
  - 確認所有測試通過，如有疑問請詢問使用者。

- [ ] 14. Lambda 進入點整合（handler.py）

  - [x] 14.1 實作 parse_request 函式
    - 從 event body 解析 symbols（1-2 個）與 question
    - 驗證 symbols ⊂ SUPPORTED_SYMBOLS、question 非空
    - 驗證失敗回傳含明確錯誤說明的回應
    - _需求：1.2、1.3、1.4、1.5_ | _Property 1、2_

  - [x] 14.2 實作 generate_run_id 函式
    - 產生格式為 run_YYYYMMDD_HHMMSS（UTC）的唯一識別碼
    - _需求：1.2_

  - [x] 14.3 實作 lambda_handler 函式
    - 串接完整流程：reset → parse → run_id → agent_loop → summarize → validate → render → export → upload → presigned URL
    - 回傳含 CORS 標頭的 JSON（report_text、evidence_download_url、log_download_url、run_id）
    - 外層 try/except 捕獲未預期錯誤，回傳 500 + CORS
    - _需求：1.1、1.6、2.5、14.1、14.2、15.1、15.2、15.3、15.4_

  - [x] 14.4 實作 main 本機測試進入點
    - 呼叫 load_local_env() 載入環境變數
    - 使用寫死的測試輸入執行完整流程
    - 輸出至 outputs/ 資料夾
    - _需求：21.1、21.2_

  - [x]* 14.5 撰寫 handler.py 的屬性測試
    - **Property 1: 有效請求必定被接受** — 1-2 個支援幣種 + 非空 question 必定通過
    - **Property 2: 無效幣種必定被拒絕** — 不在 SUPPORTED_SYMBOLS 中的代號被拒
    - **驗證: 需求 1.2、1.3、1.4、1.5**

  - [x] 14.6 串接 execution log 衍生的 report metadata 與兩條報告路徑
    - 從既有 evidence_list、execution_log、分析實際引用的 evidence_id 與能力資訊整理 analyzed_evidence_ids、evidence_capabilities、attempted_capabilities、relevant_omissions
    - 在 lambda_handler 與 main 本機路徑都透過既有 C4 coverage 參數位置傳入 metadata，並確保匯出驗證在報告儲存前執行
    - 更新本機執行摘要，顯示實際分析維度、證據筆數、canonical 獨立來源數與失敗嘗試，不顯示 x/5 或固定覆蓋百分比
    - 維持 C2 Evidence Record 及 C5 HTTP request/response 欄位與語意不變，不新增外部 API 或服務
    - _需求：12.5、12.6、12.7、13.5、13.6、13.7、13.8、13.9_ | _Property 18、19、20_

- [x] 15. 前端 JavaScript 函式（frontend/index.html）

  - [x] 15.1 實作 initCoinSelector 函式
    - 綁定五個幣種按鈕的點擊事件
    - 點擊切換 aria-pressed 狀態，最多允許選兩個
    - 維護 selectedCoins 陣列
    - _需求：17.1_

  - [x] 15.2 實作 showLoading 函式
    - 隱藏輸入面板與舊結果，顯示 #loading
    - 啟動計時器更新 #elapsed 經過秒數
    - 啟動輪播計時器每數秒更換 #loading-msg 文字
    - _需求：17.4_

  - [x] 15.3 實作 showError 函式
    - 顯示明確的錯誤訊息與處理建議（非通用「發生錯誤」）
    - _需求：17.3_

  - [x] 15.4 實作 callAnalysisApi 函式
    - fetch(API_URL, {method:"POST", headers, body})
    - 等待後端回應（可能 5-10 分鐘）
    - _需求：17.1_

  - [x] 15.5 實作 renderReport 函式
    - 用 marked.parse() 將 Markdown 轉 HTML 塞入 #report
    - 設定證據清單與執行紀錄的下載連結 href
    - 顯示 #result
    - _需求：17.5、17.6_

  - [x] 15.6 實作 handleSubmit 函式
    - 驗證：至少選一個幣種、題目不可為空
    - 呼叫 showLoading → callAnalysisApi → renderReport 或 showError
    - 無論成功失敗恢復送出按鈕、隱藏 loading
    - _需求：17.2、17.3、17.4、17.5_

  - [x] 15.7 設定 API_URL 為實際 Lambda Function URL
    - 部署後替換 placeholder 為真實的 Function URL
    - _需求：17.1_

- [x] 16. 整合測試（tests/test_local_run.py）

  - [x] 16.1 更新 run_single_case 的兩條報告路徑整合驗證
    - 驗證 Lambda 與本機流程都從 evidence/execution log 產生 report metadata，並渲染實際維度、證據筆數、canonical 獨立來源數、逐維度明細與失敗嘗試
    - 驗證 C2 Evidence Record 與 C5 HTTP 回應契約未改變，report.py 不呼叫外部 API
    - 將來源類別 >= 3 保留為 export pass/fail 斷言，另行驗證 report 不含 x/5、x/3、固定覆蓋百分比或維度分數
    - _需求：12.5、12.6、12.7、13.5、13.6、13.8、13.9_ | _Property 18、20_

  - [x] 16.2 更新 print_summary 的本機執行摘要
    - 輸出案例名稱、通過／失敗、耗時、實際分析維度、證據筆數、canonical 獨立來源數及已知失敗嘗試
    - 移除固定涵蓋類別數、x/5 與固定覆蓋百分比顯示
    - _需求：12.5、12.6、12.7_ | _Property 18_

  - [x] 16.3 實作 main 函式
    - 依序執行三個 TEST_CASES，最後印出總表
    - _需求：21.3_

- [ ] 17. 最終檢查點 — 確認完整流程
  - 確認所有測試通過，如有疑問請詢問使用者。
  - 使用 `python -m tests.test_local_run` 執行整合測試，驗證五幣種 × 三題型的完整流程。

## 備註

- 標記 `*` 的任務為選用，可在快速 MVP 時跳過
- 每個任務引用對應的需求編號以確保可追溯性
- 屬性測試驗證設計文件中的正確性屬性（Property）
- 檢查點確保漸進式驗證
- 所有工具函式遵循相同的錯誤處理模式：捕獲所有例外，回傳 error dict

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["3.4", "4.3", "5.6", "6.2", "7.3", "9.7", "10.1", "11.4"] },
    { "id": 1, "tasks": ["9.8", "10.3"] },
    { "id": 2, "tasks": ["10.4", "14.6"] },
    { "id": 3, "tasks": ["16.1"] },
    { "id": 4, "tasks": ["16.2"] }
  ]
}
```

## 17. Pipeline Presentation 跨模組整合（R2/R3/R15–R17/R20）

- [ ] 17.1 凍結 C7 v1.0 schema 與 validator，建立 single/hypothesis/comparison 三份 golden fixtures
- [ ] 17.2 串接題型判別、Phase A bounded prefetch、Phase B 補洞與 <20% 強制收斂
- [ ] 17.3 產出同源 report.md + report_data.json，驗證 verdict/信心/訊號/evidence 一致
- [ ] 17.4 前端串接三版面、Chart.js、查證摺疊、na/低資料可用率樣式與純 Markdown fallback
- [ ] 17.5 工具供應近 90 日 price/relative-strength/funding/supply series，完整序列不進 LLM summary
- [ ] 17.6 E2E:三題型各一案 + Phase A 部分失敗 + C7 組裝失敗 + Chart.js 失敗；原三交付物與下載連結始終可用
- [ ] 17.7 Demo 演練:工具時間軸→結論卡→訊號→查證→Evidence 下載，全程 <15 分鐘且不出現投資建議

依賴順序：17.1 → 17.5 → 17.2 → 17.3 → 17.4 → 17.6 → 17.7。
