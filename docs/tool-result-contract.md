# 資料工具標準結果契約（C1）

## 一、目的與適用範圍

工具覆蓋範圍、來源限制、live smoke 與遷移狀態見 [tool-capability-quality-matrix.md](./tool-capability-quality-matrix.md)。

本文件正式定義所有 `lambda/tools/` 對 Agent、Evidence 與報告層提供的共同結果格式。契約採**向後相容擴充**：既有的 `raw`、`source`、`content_reference`、`summary` 保留，新增 schema、品質與異常欄位。

第一階段強制套用於 BTC 垂直切片：

- 價格／技術：`get_price_ohlcv`、`compute_quant`
- 衍生品／流動性：`get_derivatives`、`get_orderbook_depth`
- 事件催化：`search_news`

其餘工具須逐步遷移；在遷移完成前，Evidence 層會保留舊格式相容性。

## 二、成功結果

```json
{
  "schema_version": "1.0",
  "status": "success",
  "raw": {},
  "source": "https://provider.example/api",
  "summary": "供 Agent 使用的精簡摘要",
  "content_reference": {
    "as_of": "2026-08-01T12:00:00+00:00",
    "fetched_at": "2026-08-01T12:00:10+00:00",
    "timeframe": "1d",
    "window": "14d",
    "unit": {"price": "USD"},
    "symbol": "BTC",
    "pair": "BTCUSDT",
    "provider": "Binance",
    "endpoint": "https://api.binance.com/api/v3/klines",
    "freshness_status": "fresh",
    "comparability_notes": [],
    "quality": {
      "freshness": {
        "status": "fresh",
        "age_seconds": 10,
        "max_age_seconds": 259200,
        "reference_time": "2026-08-01T12:00:10+00:00"
      },
      "reliability": {
        "attempts": 1,
        "max_attempts": 2,
        "fallback_used": false,
        "primary_provider": "Binance",
        "rate_limited": false,
        "partial": false,
        "errors": []
      },
      "comparability": {
        "status": "comparable",
        "notes": []
      }
    }
  },
  "anomaly_flags": []
}
```

### 必填欄位

| 層級 | 欄位 | 說明 |
|---|---|---|
| top-level | `schema_version` | 目前固定 `1.0` |
| top-level | `status` | `success`、`partial` 或 `error` |
| top-level | `raw` | 原始 API 回應或決定性計算結果 |
| top-level | `source` | 可回溯來源 URL、S3 key 或本地計算識別 |
| top-level | `summary` | 精簡、不可取代 Evidence 的 Agent 摘要 |
| top-level | `content_reference` | 查詢、時間、單位、品質與引用資料 |
| top-level | `anomaly_flags` | 無異常時為空陣列，不得省略 |
| content_reference | `as_of` | 資料本身代表的時間，而非只填抓取時間 |
| content_reference | `fetched_at` | 系統取得資料的 UTC 時間 |
| content_reference | `timeframe` | `snapshot`、`5m`、`8h`、`1d`、`event` 等 |
| content_reference | `window` | `snapshot`、`14d`、`90d` 或明確日期範圍 |
| content_reference | `unit` | 字串或欄位到單位的物件 |
| content_reference | `symbol` | 大寫幣種代碼；不適用時為 `MARKET` |
| content_reference | `pair` | 交易對；不適用時為 `null` |
| content_reference | `provider` | 實際成功資料來源，不填預定但失敗的來源 |
| content_reference | `endpoint` | endpoint、endpoint 陣列或 `local://` query 名稱 |
| content_reference | `freshness_status` | `fresh`、`stale` 或 `unknown` |
| content_reference | `comparability_notes` | 陣列；說明不同來源、鏈、時間窗或單位限制 |
| content_reference | `quality` | freshness、reliability、comparability 結構 |

## 三、失敗結果

```json
{
  "schema_version": "1.0",
  "status": "error",
  "error": "[tool_name] Timeout: provider did not respond",
  "source": "https://provider.example/api",
  "content_reference": {
    "as_of": null,
    "fetched_at": "2026-08-01T12:00:10+00:00",
    "timeframe": "snapshot",
    "window": "snapshot",
    "unit": {},
    "symbol": "BTC",
    "pair": "BTCUSDT",
    "provider": "Provider",
    "endpoint": "https://provider.example/api",
    "freshness_status": "unknown",
    "comparability_notes": ["資料取得失敗，無法比較"],
    "quality": {}
  },
  "anomaly_flags": []
}
```

失敗結果不得把舊資料偽裝成目前資料；若使用 fallback 成功，回傳 `success` 或 `partial`，並在 `quality.reliability` 記錄主來源錯誤與實際 provider。

## 四、Freshness 規則

Freshness 以 `reference_time - as_of` 計算，不以模型敘述判斷。歷史區間查詢以查詢結束時間作 reference；即時快照以 `fetched_at` 作 reference。

| 資料類型 | 最大資料年齡 | 超過後處理 |
|---|---:|---|
| 日線價格、技術指標 | 3 日 | 標記 stale；目前／近期題目不得無警告使用 |
| 衍生品 funding、OI | 5 分鐘 | 標記 stale |
| Order book 快照 | 60 秒 | 標記 stale |
| 市場 dominance | 1 日 | 標記 stale |
| 一般新聞 | 題目 lookback，最長 14 日 | 超出期間即過濾 |
| 官方公告 | 30 日 | 超出期間不作近期催化劑 |
| 情緒指標 | 1 日 | 標記 stale |
| 總經觀察值 | 3 日；低頻序列可另註 | 標記 stale 並說明發布頻率 |
| 未來事件日曆 | 事件時間 | 已過期事件不得列為未來催化劑 |

`as_of` 無法取得或解析時，`freshness_status=unknown`，不可自動視為 fresh。

## 五、可靠性、Timeout、Rate Limit 與 Fallback

### 共用 HTTP 預設值

- timeout：15 秒；個別慢速來源可明確覆寫，最高 30 秒。
- max attempts：2（首次 + 1 次重試）。
- 僅針對 timeout、connection error、HTTP 429、500、502、503、504 重試。
- backoff：預設 0.25 秒；若回應有合理的 `Retry-After`，優先採用但設上限。
- 4xx（429 除外）、資料格式錯誤與驗證錯誤不重試。

### 第一垂直切片 fallback

| 能力 | 主來源 | fallback | 降級紀錄 |
|---|---|---|---|
| 日線價格 | Binance | CoinGecko | `fallback_used`、主來源錯誤、實際 provider |
| 衍生品 funding/OI | Hyperliquid | Binance Futures | 同上；只有兩者皆失敗才回 error |
| 新聞／事件 | Google News + 媒體 + 官方來源 | 任一成功來源形成 partial/success | 記錄失敗 feed 與成功來源數 |
| 技術指標 | 本地決定性計算 | 無 | 價格資料失敗即 error |
| Order book | Binance Spot | 無 | error，不以 OHLCV 替代深度 |

## 六、Comparability

`quality.comparability.status` 值域：

- `comparable`：相同單位、粒度與時間窗，可直接比較。
- `limited`：可以觀察方向，但絕對值不可直接比較。
- `not_comparable`：不得形成直接大小比較。
- `unknown`：資訊不足。

例如 ETH 五個區塊交易數與 SOL 十分鐘交易數不得直接比較絕對值，必須標記 `not_comparable` 或先完成可解釋的時間正規化。

## 七、異常旗標

```json
{
  "signal_id": "A2",
  "name": "波動壓縮",
  "severity": "significant",
  "direction": "low",
  "value": 2.8,
  "unit": "%",
  "percentile": 7.0,
  "threshold": "percentile <= 10",
  "window": "20d",
  "as_of": "2026-08-01",
  "message": "布林帶寬位於近一年第 7 百分位，屬顯著壓縮"
}
```

必要欄位：`signal_id`、`name`、`severity`、`direction`、`value`、`unit`、`threshold`、`window`、`as_of`、`message`。`percentile` 無法計算時可為 `null`。

工具只負責單源異常（A1～A10）；跨來源背離仍由 Agent 使用兩側完整 evidence ID 判斷。

## 八、Evidence 與原始資料

Evidence record 除命題最低四欄位外，應保留：

- `schema_version`
- `tool_name`
- `source_url`（source 為 HTTP URL 時）
- `data_quality`
- `anomaly_flags`
- `raw_payload_path`
- `raw_payload_sha256`
- `archive_status`

原始資料封存使用下列 envelope，而不是只存 API body：

```json
{
  "schema_version": "1.0",
  "evidence_id": "完整 UUID",
  "run_id": "run_...",
  "tool_name": "get_derivatives",
  "source": "https://...",
  "fetched_at": "...",
  "related_claim": "...",
  "content_reference": {},
  "anomaly_flags": [],
  "raw": {}
}
```

雜湊以實際序列化後 envelope 的 UTF-8 bytes 計算 SHA-256，供抽查時驗證完整性。

## 九、相容性政策

- 既有四欄位成功格式不得刪除或改名。
- 新 metadata 優先新增於 `content_reference` 與頂層選用欄位。
- 舊工具若尚未遷移，Evidence 層仍可記錄，但 freshness 為 `unknown`。
- Agent 不應解析 `raw`；只接收 `summary`、完整 evidence ID 與必要品質提示。
- schema 破壞性變更需升版並同步更新 Agent、Evidence、Renderer 與測試。
