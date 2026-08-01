整理成一份可以邊做邊對照的執行手冊,七個區塊,每塊都附檢查方式。

---

## 區塊 A:地基(config.py、evidence.py、storage.py)

**包含任務**:1.1、1.2、1.3、1.4、12.1、12.2、12.3、12.4

**執行前**:`git add . && git commit -m "區塊 A 開始前"`

**執行方式**:這四個檔案彼此依賴度低,可以同時丟給 Kiro 做,或一人負責 config+evidence、另一人負責 storage。

**檢查方式**:

```python
# 1. config 能不能正確讀到環境變數
from lambda import config
print(config.SUPPORTED_SYMBOLS)   # 應該印出 ['BTC','ETH','SOL','BNB','XRP']
print(config.BASELINE_END_DATE)   # 應該印出 '2026-05-31'

# 2. evidence 的基本記錄流程
from lambda import evidence
evidence.reset_stores()
eid = evidence.log_evidence("run_001", "test_tool", "測試用途說明",
                              {"source": "test", "content_reference": {}})
print(evidence.evidence_list)      # 應該有一筆，related_claim 是你填的那句話
print(eid)                          # 應該印出一個 evidence_id

# 3. 驗證「空 related_claim 會被拒絕」這個關鍵規則
result = evidence.log_evidence("run_001", "test_tool", "", {"source": "test"})
print(len(evidence.evidence_list))  # 應該還是 1，沒有增加

# 4. storage 本機讀寫（需先放一個測試 CSV 進 data/baseline/）
from lambda import storage
df = storage.read_baseline_csv("SOL")
print(df.head())                    # 應該看到 date, open, high, low, close, volume
```

**通過標準**:四段都跑得動、印出來的東西符合預期,尤其**第 3 項一定要驗證**——這是四欄位證據機制的核心防線,如果空的 `related_claim` 沒被擋下來,後面所有證據記錄都不可信。

**通過後**:`git add . && git commit -m "完成區塊 A：地基模組"`

---

## 區塊 B:六個工具(tools/ 資料夾)

**包含任務**:2.1~2.6(quant)、3.1~3.3(price)、4.1~4.2(news)、5.1~5.5(onchain)、6.1(sentiment)、7.1~7.2(macro)

**執行前**:`git add . && git commit -m "區塊 B 開始前"`

**執行方式**:六個工具互不依賴,分工同時做。**建議順序:quant.py 最先**(不需要外部 API、不需要金鑰),接著 price.py(基準 CSV 已經有了),其餘四個依你們金鑰申請下來的順序來。

**檢查方式**:每個工具寫完立刻單獨呼叫一次,不用等其他工具:

```python
# quant.py
from lambda.tools import quant
result = quant.compute_quant("SOL", ["atr_pct", "adx"], 14, "測試")
print(result["summary"])           # 有沒有意義的文字摘要
print(result.get("error"))         # 應該是 None

# price.py
from lambda.tools import price
result = price.get_price_ohlcv("BTC", "2026-07-01", "2026-07-25", "測試")
print(result["content_reference"]) # 有沒有交易對、資料區間

# news.py（需要 CryptoPanic 金鑰）
from lambda.tools import news
result = news.search_news("ETH", 14, "測試")
print(result["summary"])

# onchain.py（五個幣種都要各測一次，因為分派邏輯是這裡的重點）
from lambda.tools import onchain
for sym in ["BTC", "ETH", "SOL", "BNB", "XRP"]:
    result = onchain.get_onchain(sym, ["active_addresses"], 7, "測試")
    print(sym, result.get("error"), result["source"])

# sentiment.py / macro.py 同樣模式測一次
```

**通過標準**:

1. 每個工具回傳的 dict 都有 `raw`、`source`、`content_reference`、`summary` 四個欄位
2. **`onchain.py` 一定要五個幣種都測過**,這是唯一有分支邏輯的工具,最容易漏掉某個分支忘記接
3. 刻意測一次**故意打錯的參數或斷網狀態**,確認回傳的是 `{"error": "..."}` 而不是直接讓程式崩潰(對應 tasks.md 裡「工具永不拋錯」這條規則)

**通過後**:`git add . && git commit -m "完成區塊 B：六個資料工具"`

---

## 區塊 C:Agent 核心(agent.py)

**包含任務**:9.1、9.2、9.3、9.4、9.5

**執行前**:`git add . && git commit -m "區塊 C 開始前"`

**執行方式**:建議每個子任務單獨 commit,這是風險最高的檔案。**不用等區塊 B 全部完成**,只要 quant.py 跟 price.py 這兩個沒有外部依賴的工具好了,就能開始測迴圈邏輯。

**檢查方式**:分階段測,不要一次測整個迴圈:

```python
# 1. 先測 build_tool_config 格式對不對
from lambda import agent
config = agent.build_tool_config()
print(config["tools"][0])   # 檢查有沒有 toolSpec，related_claim 是不是 required

# 2. 測 call_bedrock 能不能連得上（這一步驗證你的 Bedrock 權限跟 model ID 正確）
messages = [{"role": "user", "content": [{"text": "你好，請自我介紹一句話"}]}]
response = agent.call_bedrock(messages, {"tools": []})
print(response["output"]["message"])

# 3. 測完整迴圈——先用簡單問題，觀察它是否會呼叫工具、會不會正常結束
history = agent.run_agent_loop("run_test", "分析 SOL 最近的 ATR 是多少")
print(len(history))          # 對話輪數，確認不是卡在無限迴圈
print(history[-1])           # 最後一則訊息應該是 end_turn 的文字內容

# 4. 測時間/輪數上限真的有效
# 可以暫時把 MAX_AGENT_TURNS 調成 2，丟一個複雜問題，
# 確認它真的會在第 2 輪強制停止，而不是一直跑下去
```

**通過標準**:

1. 迴圈**一定會結束**,不會卡住(這是最重要的一項,寧可先用極端測試逼它超時,確認強制跳出機制真的有效)
2. `dispatch_tool_call` 回傳給模型的內容裡**沒有完整原始資料**,只有 summary 跟 evidence_id(檢查 context 有沒有膨脹)
3. 呼叫工具時,`evidence.evidence_list` 真的有新增證據(代表迴圈跟區塊 A 的記錄機制有串起來)

**通過後**:每個子任務各自 `git commit`,例如 `git commit -m "完成 9.4 run_agent_loop"`

---

## 區塊 D:報告與匯出(report.py、export.py)

**包含任務**:10.1、10.2、10.3、11.1、11.2、11.3

**執行前**:`git add . && git commit -m "區塊 D 開始前"`

**執行方式**:**可以跟區塊 C 同時進行**,不用互相等,因為它只依賴區塊 A 的 evidence 格式,不依賴 agent.py。

**檢查方式**:手動塞假資料進去測,不需要真的跑過 Agent:

```python
from lambda import report, export

fake_evidence = [
    {"evidence_id": "ev_1", "source": "test", "fetched_at": "2026-07-31T00:00:00Z",
     "content_reference": {"metric": "atr_pct", "value": 2.1}, "related_claim": "測試判斷"},
]

# 1. 報告一定要有三章節
text = report.render_report("run_001", "測試題目", "這是假的分析內容", fake_evidence)
assert "市場判斷" in text
assert "關鍵依據" in text
assert "信心說明" in text
print("三章節都在，通過")

# 2. 覆蓋率計算
coverage, has, missing = report.calculate_coverage(fake_evidence)
print(coverage, has, missing)

# 3. 匯出格式
json_str = export.export_evidence_list(fake_evidence)
import json
json.loads(json_str)   # 能被解析就代表格式正確

jsonl_str = export.export_execution_log([{"ts": "x", "tool": "y", "status": "success"}])
for line in jsonl_str.strip().split("\n"):
    json.loads(line)   # 每一行都要能單獨被解析

# 4. 自我檢查機制
passed, issues = export.validate_before_export(fake_evidence, text)
print(passed, issues)
```

**通過標準**:

1. `render_report` 產出的文字**一定包含三個章節標題**,這是命題硬性要求,用 `assert` 逼自己不要漏檢查
2. `export_execution_log` 輸出的每一行都能被 `json.loads` 單獨解析(JSONL 格式的定義就是這樣,一行壞掉會讓評審的檢查工具讀不完整個檔案)
3. 記得測 `validate_before_export`——確認它真的抓得到「只有 2 種來源類別」這種不合格狀況

**通過後**:`git add . && git commit -m "完成區塊 D：報告與匯出"`

---

## 區塊 E:整合(handler.py)

**包含任務**:14.1、14.2、14.3、14.4

**執行前**:`git add . && git commit -m "區塊 E 開始前"`；**前置條件:區塊 C 跟 D 都要先完成**

**執行方式**:建議每個子任務單獨 commit。這是第一次把所有模組串在一起,出錯機率最高。

**檢查方式**:

```python
# 1. 先測 parse_request 的驗證邏輯
from lambda import handler

# 正常案例
symbols, question = handler.parse_request({"body": '{"symbols":["SOL"],"question":"測試"}'})
print(symbols, question)

# 異常案例：幣種不支援
try:
    handler.parse_request({"body": '{"symbols":["DOGE"],"question":"測試"}'})
    print("錯誤：應該要拋出驗證失敗，但沒有")
except Exception as e:
    print("正確攔截：", e)

# 異常案例：幣種超過兩個（上次提醒過要補的檢查）
try:
    handler.parse_request({"body": '{"symbols":["BTC","ETH","SOL"],"question":"測試"}'})
    print("錯誤：應該要拒絕三個幣種")
except Exception as e:
    print("正確攔截：", e)

# 2. 直接跑 main()，這是第一次真正的端到端測試
handler.main()
# 跑完後去 outputs/ 資料夾檢查三個檔案是否都產生了
```

```bash
ls outputs/
cat outputs/report.md          # 眼睛看一下報告讀起來順不順
cat outputs/evidence_list.json | python -m json.tool   # 格式化印出來檢查
head -3 outputs/execution_log.jsonl
```

**通過標準**:

1. 兩個異常案例都要**真的被攔截**,尤其「幣種超過兩個」這條之前提醒過容易漏掉
2. `main()` 跑完之後,三個檔案**都要存在且內容非空**
3. 報告內文用人類的眼睛讀一遍,確認邏輯讀起來合理,不是機器檢查得過但內容莫名其妙

**通過後**:`git add . && git commit -m "完成區塊 E：Lambda 整合"`

---

## 區塊 F:前端(index.html)

**包含任務**:15.1~15.6(可與區塊 A~E 全程平行)、15.7(最後才做)

**執行前**:`git add . && git commit -m "區塊 F 開始前"`

**執行方式**:完全獨立,誰都可以隨時做,不用等後端。

**檢查方式**:直接雙擊打開 `frontend/index.html`,用瀏覽器手動操作:

```
1. 點幣種按鈕 → 顏色有沒有正確切換(aria-pressed)？
2. 連續點三個幣種 → 是不是真的擋在最多兩個？
3. 什麼都不選直接按送出 → 有沒有跳出「請至少選擇一個幣種」？
4. 題目欄位空白直接送出 → 有沒有跳出對應錯誤？
5. 打開瀏覽器開發者工具（F12）的 Console 分頁，
   看點擊互動時有沒有噴紅字錯誤
```

在 15.7(填真正的 API_URL)完成前,`callAnalysisApi` 一定會失敗——**這是預期行為**,此時重點檢查 `showError()` 有沒有顯示出清楚的錯誤訊息,而不是整個頁面卡死沒反應。

**通過標準**:五項手動操作都符合預期,尤其錯誤訊息要看得懂、不能是空白或 undefined。

**通過後**:`git add . && git commit -m "完成區塊 F：前端互動邏輯"`

---

## 區塊 G:收尾(整合測試 + 實際部署)

**包含任務**:16.1~16.3 + 實際 AWS 部署

**前置條件**:區塊 A~F 全部完成

**執行方式**:

```bash
# 1. 本機跑完整的五幣種 × 三題型測試
python -m tests.test_local_run

# 2. 確認沒問題後才部署
./scripts/package_lambda.sh
aws lambda update-function-code --function-name 你的function名稱 --zip-file fileb://function.zip

# 3. 部署完拿到 Function URL，回頭做 15.7
# 把 index.html 裡的 API_URL 換成真的網址
aws s3 cp frontend/index.html s3://你的前端bucket/index.html
```

**檢查方式**:

1. `test_local_run.py` 印出的總表,三個案例都要通過,**特別看比較分析(雙幣種)那個案例**——這是最容易因為輸入形狀不同而漏測出 bug 的地方
2. 部署完後,**打開真正的前端網址**(不是本機檔案),完整跑一次流程:選幣種 → 輸入題目 → 送出 → 等待 → 看到報告 → 點下載連結
3. 這一輪如果順利跑完,就是可以錄「執行錄製影片」的時候了

**通過後**:`git add . && git commit -m "完成區塊 G：整合測試與部署"`,接著才考慮要不要合併回 main。

---

## 全部串起來的時間軸提示

```
A → B(平行分工) → checkpoint → C 和 D(平行) → E → F(全程平行,15.7最後) → G
```

**如果時間真的不夠,砍的優先序是**:先砍區塊 B 裡的 sentiment.py 跟 macro.py(README 裡本來就標可選),再砍區塊 D 的美化細節,**絕對不要砍區塊 A、C、E**——這三塊是「系統能不能動」的骨幹,砍了就等於沒有可交的東西。