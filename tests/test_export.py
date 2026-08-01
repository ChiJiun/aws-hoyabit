"""
test_export.py — export_evidence_list 函式的單元測試
"""

import json
import csv
import io
import sys
import os

# 把 lambda 目錄加入 path 以便直接匯入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

from export import export_evidence_list


# 測試用的 Evidence Record 資料
SAMPLE_EVIDENCE = [
    {
        "evidence_id": "ev-001",
        "source": "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=1d",
        "fetched_at": "2026-07-30T14:15:30Z",
        "content_reference": {"pair": "SOLUSDT", "range": "2026-06-01~2026-07-30", "rows": 60},
        "related_claim": "需要最近兩個月的日線資料來計算波動率指標",
    },
    {
        "evidence_id": "ev-002",
        "source": "https://cryptopanic.com/api/v1/posts/",
        "fetched_at": "2026-07-30T14:16:00Z",
        "content_reference": {"currency": "SOL", "results_count": 5},
        "related_claim": "查看近期是否有重大新聞影響價格走勢",
    },
]


def test_json_format_default():
    """預設 JSON 格式輸出，每筆含五個欄位"""
    result = export_evidence_list(SAMPLE_EVIDENCE)
    parsed = json.loads(result)

    assert isinstance(parsed, list)
    assert len(parsed) == 2

    # 檢查每筆都包含五個必要欄位
    for record in parsed:
        assert "evidence_id" in record
        assert "source" in record
        assert "fetched_at" in record
        assert "content_reference" in record
        assert "related_claim" in record

    # 驗證欄位值正確
    assert parsed[0]["evidence_id"] == "ev-001"
    assert parsed[0]["source"] == "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=1d"
    assert parsed[0]["content_reference"]["pair"] == "SOLUSDT"


def test_csv_format():
    """as_csv=True 時輸出 CSV 格式，含標題列"""
    result = export_evidence_list(SAMPLE_EVIDENCE, as_csv=True)

    # 用 csv reader 解析
    reader = csv.reader(io.StringIO(result))
    rows = list(reader)

    # 標題列 + 2 筆資料
    assert len(rows) == 3
    assert rows[0] == ["evidence_id", "source", "fetched_at", "content_reference", "related_claim"]

    # content_reference 應為 JSON 字串
    content_ref = json.loads(rows[1][3])
    assert content_ref["pair"] == "SOLUSDT"
    assert content_ref["rows"] == 60


def test_empty_list_json():
    """空清單時回傳空 JSON 陣列"""
    result = export_evidence_list([])
    parsed = json.loads(result)
    assert parsed == []


def test_empty_list_csv():
    """空清單時回傳僅含標題列的 CSV"""
    result = export_evidence_list([], as_csv=True)
    reader = csv.reader(io.StringIO(result))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0] == ["evidence_id", "source", "fetched_at", "content_reference", "related_claim"]


def test_missing_fields_graceful():
    """記錄缺少某些欄位時不會拋錯，用預設值填補"""
    incomplete = [{"evidence_id": "ev-incomplete", "source": "test"}]
    result = export_evidence_list(incomplete)
    parsed = json.loads(result)
    assert parsed[0]["fetched_at"] == ""
    assert parsed[0]["content_reference"] == {}
    assert parsed[0]["related_claim"] == ""


def test_csv_missing_fields_graceful():
    """CSV 格式下缺少欄位也不會拋錯"""
    incomplete = [{"evidence_id": "ev-incomplete"}]
    result = export_evidence_list(incomplete, as_csv=True)
    reader = csv.reader(io.StringIO(result))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[1][0] == "ev-incomplete"


def test_unicode_content():
    """中文內容正確保留（ensure_ascii=False）"""
    records = [{
        "evidence_id": "ev-zh",
        "source": "https://example.com",
        "fetched_at": "2026-07-30T14:15:30Z",
        "content_reference": {"描述": "測試中文"},
        "related_claim": "驗證中文輸出是否正確",
    }]
    result = export_evidence_list(records)
    # 中文字元不該被轉義
    assert "驗證中文輸出是否正確" in result
    assert "測試中文" in result


if __name__ == "__main__":
    test_json_format_default()
    test_csv_format()
    test_empty_list_json()
    test_empty_list_csv()
    test_missing_fields_graceful()
    test_csv_missing_fields_graceful()
    test_unicode_content()
    print("所有測試通過！")


# === validate_before_export 測試 ===

from export import validate_before_export


# 建立完整且多來源的證據清單（可通過全部檢查）
VALID_EVIDENCE = [
    {
        "evidence_id": "ev-001",
        "source": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT",
        "fetched_at": "2026-07-30T14:15:30Z",
        "content_reference": {"pair": "BTCUSDT", "rows": 30},
        "related_claim": "取得 BTC 價格走勢",
    },
    {
        "evidence_id": "ev-002",
        "source": "https://cryptopanic.com/api/v1/posts/?currencies=BTC",
        "fetched_at": "2026-07-30T14:16:00Z",
        "content_reference": {"results_count": 5},
        "related_claim": "查看 BTC 近期新聞",
    },
    {
        "evidence_id": "ev-003",
        "source": "https://mempool.space/api/blocks",
        "fetched_at": "2026-07-30T14:17:00Z",
        "content_reference": {"blocks": 10},
        "related_claim": "觀察 BTC 鏈上活動",
    },
    {
        "evidence_id": "ev-004",
        "source": "https://api.alternative.me/fng/",
        "fetched_at": "2026-07-30T14:18:00Z",
        "content_reference": {"value": 65, "classification": "Greed"},
        "related_claim": "取得市場情緒指數",
    },
]

CLEAN_ANALYSIS = "BTC 近期走勢震盪，鏈上活動增加，市場情緒偏貪婪。綜合來看短期偏多但需留意風險。"


def test_validate_all_pass():
    """所有檢查通過時回傳 (True, [])"""
    passed, failures = validate_before_export(VALID_EVIDENCE, CLEAN_ANALYSIS)
    assert passed is True
    assert failures == []


def test_validate_missing_fields():
    """欄位不齊備時回傳相應錯誤"""
    bad_evidence = [
        {"evidence_id": "ev-bad", "source": "", "fetched_at": "", "content_reference": {}, "related_claim": ""},
    ]
    passed, failures = validate_before_export(bad_evidence, CLEAN_ANALYSIS)
    assert passed is False
    assert any("缺少欄位" in f for f in failures)


def test_validate_category_insufficient():
    """來源類別數不足 3 時報告未通過"""
    # 只有 price 類別
    single_category = [
        {
            "evidence_id": "ev-001",
            "source": "https://api.binance.com/api/v3/klines",
            "fetched_at": "2026-07-30T14:15:30Z",
            "content_reference": {"pair": "BTCUSDT"},
            "related_claim": "取得價格",
        },
        {
            "evidence_id": "ev-002",
            "source": "https://api.coingecko.com/v3/coins/bitcoin",
            "fetched_at": "2026-07-30T14:16:00Z",
            "content_reference": {"coin": "bitcoin"},
            "related_claim": "備用價格來源",
        },
    ]
    passed, failures = validate_before_export(single_category, CLEAN_ANALYSIS)
    assert passed is False
    assert any("來源類別數不足" in f for f in failures)


def test_validate_forbidden_phrases():
    """含投資建議語句時報告未通過"""
    bad_analysis = "根據分析結果，建議買進 BTC，目標價 100000 美元。"
    passed, failures = validate_before_export(VALID_EVIDENCE, bad_analysis)
    assert passed is False
    assert any("投資建議語句" in f for f in failures)


def test_validate_paid_only():
    """僅有付費來源時報告未通過"""
    paid_only = [
        {
            "evidence_id": "ev-001",
            "source": "https://api.coingecko.com/v3/coins/bitcoin",
            "fetched_at": "2026-07-30T14:15:30Z",
            "content_reference": {"coin": "bitcoin"},
            "related_claim": "取得價格",
        },
        {
            "evidence_id": "ev-002",
            "source": "https://cryptopanic.com/api/v1/posts/",
            "fetched_at": "2026-07-30T14:16:00Z",
            "content_reference": {"results_count": 3},
            "related_claim": "查看新聞",
        },
        {
            "evidence_id": "ev-003",
            "source": "https://api.etherscan.io/v2/api?module=account",
            "fetched_at": "2026-07-30T14:17:00Z",
            "content_reference": {"address": "0x..."},
            "related_claim": "鏈上資料",
        },
    ]
    passed, failures = validate_before_export(paid_only, CLEAN_ANALYSIS)
    assert passed is False
    assert any("付費來源為唯一依據" in f for f in failures)


def test_validate_empty_evidence():
    """空證據清單時，類別數不足應被偵測"""
    passed, failures = validate_before_export([], CLEAN_ANALYSIS)
    assert passed is False
    assert any("來源類別數不足" in f for f in failures)


def test_validate_multiple_forbidden_phrases():
    """多個禁止語句都被偵測到"""
    bad_analysis = "建議持有 ETH，應該買入更多，賣出 BTC。"
    passed, failures = validate_before_export(VALID_EVIDENCE, bad_analysis)
    assert passed is False
    # 確認包含投資建議語句的錯誤
    advice_failure = [f for f in failures if "投資建議語句" in f]
    assert len(advice_failure) == 1
    # 確認多個語句被列出
    assert "建議持有" in advice_failure[0]
    assert "賣出" in advice_failure[0]
    assert "應該買" in advice_failure[0]


def test_validate_exception_handling():
    """傳入非預期資料型態不會拋錯"""
    passed, failures = validate_before_export(None, None)
    assert passed is False
    assert len(failures) > 0


if __name__ == "__main__":
    test_validate_all_pass()
    test_validate_missing_fields()
    test_validate_category_insufficient()
    test_validate_forbidden_phrases()
    test_validate_paid_only()
    test_validate_empty_evidence()
    test_validate_multiple_forbidden_phrases()
    test_validate_exception_handling()
    print("validate_before_export 所有測試通過！")
