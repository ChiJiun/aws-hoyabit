"""demo_server.py 的多維度模擬報告靜態測試。"""

from scripts.demo_server import MOCK_REPORT


def test_mock_report_demonstrates_multidimensional_evidence():
    assert "### 多維度分析摘要" in MOCK_REPORT
    assert "實際分析維度" in MOCK_REPORT
    assert "引用證據筆數" in MOCK_REPORT
    assert "獨立來源數" in MOCK_REPORT
    assert "各維度證據與來源" in MOCK_REPORT
    for dimension in ("價格", "技術指標", "鏈上", "情緒", "新聞與公告", "總體經濟"):
        assert f"**{dimension}**" in MOCK_REPORT
    for evidence_id in ("EVD-001", "EVD-004", "EVD-005", "EVD-006", "EVD-008"):
        assert evidence_id in MOCK_REPORT
    assert "Demo 聲明" in MOCK_REPORT or "Demo 模擬聲明" in MOCK_REPORT
    assert "CryptoPanic" not in MOCK_REPORT
    assert "Google News RSS" in MOCK_REPORT
    assert "google-news-rss + media-rss" in MOCK_REPORT
    assert "未執行回測" in MOCK_REPORT
    assert "68% 機率" not in MOCK_REPORT
    assert "40% 機率" not in MOCK_REPORT


def test_mock_report_has_no_fixed_coverage_copy():
    for forbidden in ("五類資料", "100%", "5/5", "4/5", "資料覆蓋率"):
        assert forbidden not in MOCK_REPORT
