# core-infrastructure 設計

## 定位
全專案最底層,無內部依賴。對外只暴露 contracts.md 的 C2(Evidence API)、C3(Storage API)、C6(環境變數)。**本模組介面凍結後,其他五個模組才能安心平行開發,因此最先完成、最少變動。**

## config.py
- pydantic 風格或 dataclass 的單一 Settings 物件;`load_local_env()` 用 python-dotenv
- 所有常數(SUPPORTED_SYMBOLS、MAX_AGENT_TURNS、TIME_BUDGET_SECONDS、BASELINE_END_DATE)集中此處
- 提供 `missing_vars() -> list[str]` 供 handler 啟動自檢

## evidence.py
- 模組層級全域 `evidence_list: list[dict]`、`execution_log: list[dict]`(單一 Lambda 內單執行緒,可接受)
- `reset_stores()`:每次 handler 進入時呼叫(R2.6)
- `log_evidence()`:驗證 related_claim(非空、len≥10)→ 產 UUID evidence_id → 補 fetched_at → 呼叫 storage.save_raw_payload 封存 raw → append → 回傳 id
- `log_execution_step()`:append {timestamp, tool_name, status, elapsed_ms, evidence_id, note}

## storage.py
- boto3 s3 client 延遲初始化;`IS_LOCAL` 由環境變數判斷,本機讀寫本地路徑
- 四個函式簽名見契約 C3,不多不少;presigned URL 過期預設 3600 秒

## 錯誤處理
- storage 失敗拋出明確例外給 handler 統一處理(基礎設施失敗 = 執行失敗,不可吞)
- evidence 驗證失敗回傳錯誤訊息 dict,不拋例外(讓 Agent 迴圈能糾正 LLM)

## 測試重點(屬性)
P4 reset 後兩清單為空|P7 四欄位齊備|P8 空 related_claim 不入列|P9 evidence_id 唯一|P10 執行紀錄含必要欄位


## Pipeline Presentation 設計增補

新增 `lambda/report_schema.py`（或同等無業務依賴模組）：

```python
C7_SCHEMA_VERSION = "1.0"
QUESTION_TYPES = {"single_integration", "hypothesis", "comparison"}
STANCE_VALUES = {"bullish", "bearish", "neutral", "mixed"}
DIMENSION_STATES = {"strong", "weak", "neutral", "na"}
SIGNAL_LEVELS = {"red", "yellow"}

def validate_report_data(value, evidence_ids=None):
    """Return list[dict(path, code, message)]; never mutate input."""
```

驗證採小型明確 Python 檢查，不新增 JSON Schema runtime 依賴。日期統一 ISO 8601，series point 支援 `[date, value]`，value 必須 finite；同一 series 日期不得重複且須升冪，超過 90 日回 error。comparison 必須兩 symbols 且 comparison object 非 null；其他題型的 comparison 為 null；hypothesis 同理。

模組 import 副作用為零且不讀環境變數。測試使用 table-driven invalid fixtures 覆蓋每個 error path、extension field、input 不變性與 validator never-raises property。
