# 資料管線與呈現架構規劃

目的:從「來源 → 蒐集 → 處理 → 呈現」定義端到端流程,支援三種題型自適應版面與視覺化。
基於現有程式碼(11 個工具、report.py 渲染、前端卡片骨架)的增量規劃,不推翻現有架構。

## 一、整體流程(四層)

```
題目 + 幣種
   │
   ▼
[0. 題型判別] handler/agent:single_integration | hypothesis | comparison
   │
   ▼
[1. 蒐集層] 兩段式:
   Phase A 保底預抓(並行、決定性):依「題型×幣種矩陣」抓必備組
   Phase B Agent 補洞(迭代、自主):LLM 依題目語意決定加抓什麼
   │  每次抓取 → evidence(四欄位)+ execution_log + raw 封存
   ▼
[2. 處理層] 決定性計算 → LLM 推理:
   quant 指標+百分位 → anomaly_flags(A 類)→ LLM 跨源背離核對(B 類)
   → 事實/推論/結論三層分析 → summarize 收斂
   │
   ▼
[3. 呈現層] 一份結構化 report_data.json 驅動三種輸出:
   report.md(評分主體)+ 前端視覺化版面(Demo)+ evidence/log 下載
```

## 二、蒐集層:題型 × 來源矩陣

### Phase A 保底預抓(不等 LLM,進場即並行開抓,~90 秒內完成)
所有題型共同必抓(per 幣種):價格 OHLCV(CSV+Binance 補)、quant 指標包、衍生品包(HL 資金費率/OI + Binance 多空比)、F&G、Google News RSS 近 7 天、對應鏈上包、FRED 核心三項(DXY/10Y/FFR)。

題型加抓:
| 題型 | 額外保底 |
|---|---|
| single_integration | DefiLlama 穩定幣供給、Polymarket 相關事件、幣種 playbook 項目(ETF 流量 for BTC/ETH、escrow for XRP…) |
| hypothesis | 同上 + 針對假設關鍵字的新聞定向查詢(正反兩組關鍵字各查一輪) |
| comparison | 兩幣各一整套 + 相關係數(quant)+ 相對強弱(價格比值序列)+ 兩幣市佔率變化 |

### Phase B Agent 補洞(剩餘時間預算內,最多 N 輪)
LLM 看過 Phase A 摘要後,自主決定:追新聞細節、查特定鏈上事件、Deribit IV(若波動異常)、SEC EDGAR(若監管相關)、深度快照(若量能異常)。
規則:Phase B 每輪呼叫前檢查時間預算;預算 <20% 強制進入收斂。

設計理由:純 Agent 迴圈讓 LLM 從零決定抓什麼,慢且不穩;純固定管線又答不了「假設驗證」這種語意題。保底+補洞兼顧 15 分鐘穩定性與題型彈性。

## 三、處理層:從原始資料到判斷

1. **正規化**:各工具內部完成(統一 C1 契約,summary ≤500 tokens,數字含百分位)
2. **單源異常標記**:工具自帶 anomaly_flags(門檻在 config.ANOMALY_THRESHOLDS)
3. **跨源背離核對**(LLM,SYSTEM_PROMPT 檢查清單 B1–B6):逐項回答 有/無/資料不足,引用兩側 evidence_id
4. **題型專屬推理要求**:
   - single:五維度(價格動能/槓桿結構/鏈上/情緒/總經)各給一個狀態判定 + 整體一致性評估
   - hypothesis:證據分「支持/反對/中性」三欄,最終判斷必須說明為何一方勝出(或為何無法判定)
   - comparison:同一維度並排比較,差異必須量化(如「A 的 OI 百分位 92 vs B 的 41」),結尾給「什麼條件下優先關注誰」
5. **收斂**:summarize_final_analysis 依題型模板整理 → 三章節保證
6. **品質門**:validate_before_export(禁語/類別數/孤兒引用/付費來源)

## 四、呈現層(核心新增:結構化資料驅動)

### 4.1 report_data.json(新契約 C7,report.py 產出,handler 隨回應下發)
```json
{
  "question_type": "single_integration | hypothesis | comparison",
  "symbols": ["BTC"],
  "verdict": {"text": "...", "stance": "bullish|bearish|neutral|mixed", "confidence": 0.62,
               "confidence_label": "中等", "invalidation": "什麼條件會推翻"},
  "dimensions": [
    {"name": "價格動能", "state": "strong|weak|neutral|na", "headline": "近兩週 +8.2%(波動第74百分位)",
     "evidence_ids": ["ev_3"], "per_symbol": {"BTC": {...}, "ETH": {...}}}
  ],
  "signals": [
    {"level": "red|yellow", "title": "量價背離", "detail": "...", "metrics": [{"label":"量能Z","value":-1.1,"percentile":18}],
     "evidence_ids": ["ev_4","ev_9"], "caveat": "..."}
  ],
  "checked_normal": ["帶寬 P54", "鏈上活躍 ±6%", "BTC相關性 0.81"],
  "hypothesis": {"statement": "...", "supporting": [...], "opposing": [...], "verdict_reason": "..."},   // 僅 hypothesis
  "comparison": {"rows": [{"dimension":"槓桿結構","a":{...},"b":{...},"edge":"A"}], "when_prefer_a": "...", "when_prefer_b": "..."},  // 僅 comparison
  "series": {"price": {"BTC": [[date, close], ...]}, "funding": {...}},   // 近 90 日,前端畫圖用
  "coverage": {"pct": 86, "got": [...], "missing": [...]},
  "watchlist": [{"event": "FOMC", "date": "2026-08-18", "why": "..."}]
}
```
原則:**Markdown 給人讀、report_data 給機器畫**,兩者由同一份分析產生,內容一致;前端絕不自己算數據。

### 4.2 版面模板(前端依 question_type 切換)

**共同頂部(所有題型)**:結論卡(stance 色框 + 信心儀表 + 推翻條件)→ 五維度狀態列(色塊條,一眼掃完)→ 異常訊號卡片區(紅/黃邊框、⚪ 摺疊清單)

**single_integration**:頂部 + 價格 sparkline(90d,標注異常日)+ 各維度展開卡(headline + 關鍵數字 + 查證摺疊)+ 觀察清單時間軸
**hypothesis**:頂部 + 「證據天平」雙欄(支持 | 反對,各卡片含強度標記)+ 判定理由框 + 「無法判定時」誠實聲明樣式
**comparison**:頂部(結論改為相對判斷)+ 雙幣並排欄(同維度左右對照,優勢側高亮)+ 相關性/相對強弱圖 + 「何時關注誰」決策框

### 4.3 視覺化技術
- 前端維持單檔 + CDN:marked.js(已有)+ **Chart.js**(sparkline、相對強弱線、信心/雷達)— 皆 cdnjs 可載
- 手繪已有的 conf-gauge/radar 可保留,series 數據來自 report_data
- report.md 內視覺化:維度狀態用 emoji 色塊表格(🟢🟡🔴⚪)、對比題用並排 Markdown 表 — 保證純 md 也可讀(評審可能只看 md)
- Demo 錄影動線:輸入 → 工具呼叫時間軸滾動(執行感)→ 結論卡浮現 → 捲過訊號卡 → 點開一個「查證」摺疊展示可回溯性 → 下載 evidence

### 4.4 降級呈現
某維度資料缺失 → 該維度卡顯示「⚫ 無資料(原因)」而非隱藏;coverage <60% → 結論卡自動加「低覆蓋警示」邊帶。誠實降級本身就是評分點(信心校準)。

## 五、實作切分(對應 specs 增補)

| 模組 | 新增工作 | 優先級 |
|---|---|---|
| agent-orchestrator | 題型判別(規則+LLM 兜底);Phase A 並行預抓調度;題型專屬 prompt 模板 | P0 |
| report-delivery | build_report_data():從分析文字+evidence 組裝 C7 JSON;md 模板加維度狀態表/對比表/天平段 | P0 |
| frontend-ui | 三版面模板 + Chart.js 圖表 + 查證摺疊 + 降級樣式 | P0 |
| core-infrastructure | C7 schema 常數與驗證(欄位齊備檢查) | P1 |
| tools 兩組 | 確保 series 數據可輸出(價格/資金費率近 90d 序列存 raw,supply series 給 report) | P1 |

風險控制:report_data 組裝失敗時,前端 fallback 到純 marked 渲染 report_text — 視覺化是加分項,絕不能成為單點故障。
