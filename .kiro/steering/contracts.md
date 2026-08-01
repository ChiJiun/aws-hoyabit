---
inclusion: always
---

# 模組間契約(低耦合的唯一依據 — 改動需全隊同意)

模組之間只透過以下契約互動。實作細節各模組自理,但契約欄位名、型別、語意不可私改。

## C1. Data Tool 回傳契約(所有 lambda/tools/*.py)
成功:
```python
{"raw": <原始API回應>, "source": "<實際呼叫的URL或來源名稱>",
 "content_reference": "<引用片段/查詢參數/指標數值>", "summary": "<給模型的精簡摘要>"}
```
失敗:`{"error": "<可讀的錯誤說明>"}`
規則:絕不拋出未處理例外;summary 控制在 ~500 tokens 內;每個工具的 inputSchema 必含必填參數 `related_claim`。
選用欄位 `anomaly_flags: list[dict]`:工具自行偵測的單源異常(見 docs/anomaly-signal-plan.md 表 A),每項含 {signal, direction, value, percentile, threshold};無異常時為空列表。向後相容,消費端不得假設必存在。

## C2. Evidence API(lambda/evidence.py 提供)
```python
log_evidence(fetch_result: dict, related_claim: str, run_id: str) -> str   # 回傳 evidence_id;related_claim 空/過短則拒絕
log_execution_step(tool_name, status, elapsed_ms, evidence_id=None, note=None) -> None
reset_stores() -> None   # 每次執行開頭必呼叫(Lambda 容器重用)
```
Evidence Record 固定四欄位:source、fetched_at(UTC ISO 8601)、content_reference、related_claim(+ 系統欄位 evidence_id)。

## C3. Storage API(lambda/storage.py 提供)
```python
read_baseline_csv(symbol) -> pd.DataFrame        # S3: baseline/{symbol}USDT_daily_ohlcv.csv;本機: data/baseline/
save_raw_payload(run_id, evidence_id, payload)   # S3: runs/{run_id}/raw/{evidence_id}.json
save_output_file(run_id, filename, content)      # S3: runs/{run_id}/{filename}
generate_download_link(run_id, filename, expires=3600) -> str
```

## C4. Agent → Report 契約
agent.py 產出 `analysis_text: str`(已含事實→推論→結論結構);report.render_report(analysis_text, evidence_list, missing_sources, coverage) 產出 Markdown,三章節(市場判斷/關鍵依據/信心說明)由模板保證存在。

## C5. Handler HTTP 回應契約(frontend 唯一依賴)
成功 200:
```json
{
  "run_id": "...",
  "report_text": "<markdown>",
  "report_data": {},
  "evidence_download_url": "<presigned>",
  "log_download_url": "<presigned>"
}
```
`report_data` 遵循 C7；若 C7 組裝或驗證失敗可為 `null` 或省略，`report_text` 與下載連結仍須正常回傳。失敗 4xx/5xx：`{"error": "<明確錯誤說明>"}`；所有回應必含 CORS 標頭。
請求格式：`POST {"symbols": ["BTC"] 或 ["BTC","ETH"], "question": "<非空字串>"}`。

## C7. 結構化報告資料(report_data.json)

`report.build_report_data()` 產出，Handler 將它存為 `runs/{run_id}/report_data.json` 並透過 C5 的 `report_data` 欄位下發。Frontend 視覺化只能使用 C7，不得從 Markdown 抽值或自行計算。

```json
{
  "schema_version": "1.0",
  "question_type": "single_integration | hypothesis | comparison",
  "symbols": ["BTC"],
  "verdict": {
    "text": "...",
    "stance": "bullish | bearish | neutral | mixed",
    "confidence": 0.62,
    "confidence_label": "中等",
    "invalidation": "..."
  },
  "dimensions": [{
    "name": "價格動能",
    "state": "strong | weak | neutral | na",
    "headline": "...",
    "evidence_ids": ["ev_..."],
    "per_symbol": {"BTC": {}}
  }],
  "signals": [{
    "level": "red | yellow",
    "title": "...",
    "detail": "...",
    "metrics": [{"label": "...", "value": 0, "percentile": 50}],
    "evidence_ids": ["ev_..."],
    "caveat": "..."
  }],
  "checked_normal": ["..."],
  "hypothesis": null,
  "comparison": null,
  "series": {"price": {"BTC": [["2026-08-01", 100.0]]}},
  "coverage": {"pct": 86, "got": ["price"], "missing": [{"capability": "macro", "reason": "timeout"}]},
  "watchlist": [{"event": "FOMC", "date": "2026-08-18", "why": "..."}]
}
```

規則：
- `schema_version`、`question_type`、`symbols`、`verdict`、`dimensions`、`signals`、`checked_normal`、`series`、`coverage`、`watchlist` 為必要欄位。
- `symbols` 必須與請求一致；single/hypothesis 恰為 1 個，comparison 恰為 2 個。
- `hypothesis` 僅在 hypothesis 題型為物件，包含 `statement/supporting/opposing/verdict_reason`；其他題型為 `null`。
- `comparison` 僅在 comparison 題型為物件，包含 `rows/when_prefer_a/when_prefer_b`；其他題型為 `null`。
- `confidence` 為 0–1；`evidence_ids` 必須存在於 C2；`series` 最多提供近 90 日且日期升冪。
- `coverage.pct` 是題目相關 Phase A 能力的資料可用率，不是固定維度覆蓋率、報告分數或信心；無適用能力時為 `null`。
- C7 與 report.md 必須來自同一份分析並保持 verdict、信心、訊號與引用一致。
- C7 組裝或驗證失敗不得阻斷 report.md、evidence_list.json、execution_log.jsonl 匯出；必須記錄失敗並採純 Markdown 降級。

## C6. 環境變數(config.py 統一讀取,他處不得直接 os.environ)
AWS_REGION、BEDROCK_MODEL_ID、DATA_BUCKET、BASELINE_END_DATE、MAX_AGENT_TURNS、TIME_BUDGET_SECONDS、各資料源 API 金鑰(COINGECKO_API_KEY、ETHERSCAN_API_KEY、HELIUS_API_KEY、FRED_API_KEY)
