"""
test_local_run.py — 本機整合測試

目的：在部署到 AWS 之前，先在本機把整條「輸入 → Agent 迴圈 → 報告產出」
的流程跑過一輪，確認邏輯正確。這裡不是要取代 handler.py 的 main()，
而是把 main() 針對「五個幣種 × 三種題型」重複呼叫，確保現場不管抽到
什麼組合都測試過。

執行方式：在專案根目錄下跑
    python -m tests.test_local_run
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

import handler  # noqa: E402


# 命題的三種範例題型，對應到不同的輸入形狀（尤其比較分析需要兩個幣種）
TEST_CASES = [
    {
        "name": "多源整合－單幣種",
        "symbols": ["SOL"],
        "question": "分析 SOL 過去兩週的市場表現，整合價格走勢、鏈上活躍度、"
                     "主要新聞事件與社群討論熱度，給出整體市場狀態判斷，"
                     "並說明各類資料之間的一致程度。",
    },
    {
        "name": "假設驗證－單幣種",
        "symbols": ["BTC"],
        "question": "市場上有聲音認為 BTC 短期內將維持盤整、缺乏明確方向，"
                     "請蒐集支持與反對此觀點的證據，並說明你最終的判斷與理由。",
    },
    {
        "name": "比較分析－雙幣種",
        "symbols": ["ETH", "SOL"],
        "question": "比較 ETH 與 SOL 在當前宏觀環境下各自的市場位置與風險特徵，"
                     "說明兩者在流動性、市場關注度或風險敞口上的主要差異，"
                     "以及在什麼條件下各自更值得優先關注。",
    },
]


def run_single_case(case):
    # 功能：執行單一測試案例，呼叫 handler 內部邏輯（不經過 Lambda event 格式），
    #      並印出關鍵檢查結果，方便人工確認。
    # 檢查項目建議包含：
    #   1. 是否有拋出未處理的例外
    #   2. 是否真的產出 report_text，且長度不為 0
    #   3. evidence_list 是否至少涵蓋 3 種不同的 source_type
    #      （對應命題「來源類型是否多樣」的評分觀察點）
    #   4. 是否有任何 claim 找不到對應的 evidence_id（孤兒結論）
    #   5. 整體耗時是否在 TIME_BUDGET_SECONDS 之內
    # 印出：案例名稱、通過/失敗、耗時、若失敗則印出原因
    pass


def print_summary(results):
    # 功能：所有案例跑完後，印出一張總表，方便一次看出哪些案例沒過。
    # 欄位：案例名稱、通過與否、耗時、證據筆數、涵蓋的資料類別數
    pass


def main():
    # 功能：依序執行 TEST_CASES 裡的每個案例，最後印出總表。
    # 建議：先跑「多源整合－單幣種」這個最簡單的案例，
    #      確認基本流程沒問題後，再跑其餘案例。
    results = []
    for case in TEST_CASES:
        result = run_single_case(case)
        results.append(result)
    print_summary(results)


if __name__ == "__main__":
    main()