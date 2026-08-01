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