"""
demo_server.py — 展示用模擬伺服器

不需要任何 API 金鑰或 AWS 設定，直接回傳一份寫好的模擬報告，
用於展示前端最終呈現效果。

使用方式：
  python scripts/demo_server.py
  瀏覽 http://localhost:8080
"""

import json
import time
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MOCK_REPORT = '''# 加密市場分析報告

> **Demo 模擬聲明**：本報告所有數值、敘事與 Evidence ID 都是介面展示用假資料，不代表即時市場結果或已執行的回測。
> **分析題目**：綜合價格走勢、鏈上活躍度與市場情緒，分析 BTC 目前的市場狀態與短期可能方向。
> **執行 ID**：run_20260801_demo
> **產出時間**：2026-08-01 12:00 UTC

---

## 市場判斷

**BTC 目前處於「高波動蓄勢」狀態，短期偏向上行但需關注 FOMC 事件風險。**

綜合多個題目相關維度的交叉驗證結果：價格技術面呈現布林帶收窄後放量突破，鏈上活躍地址數連續三週攀升至年度高點，情緒指標從中性區間升至「貪婪」區域。然而，距離 FOMC 利率決議僅剩 12 天，且美元指數近期走強，構成潛在逆風。

**整體判斷**：偏多但非一面倒，需密切觀察 8 月 13 日 CPI 數據是否超預期。

---

## 關鍵依據

### 事實層（Evidence-backed）

| # | 依據 | 來源 | Evidence ID |
|---|------|------|-------------|
| 1 | BTC 收盤價 $98,450，14日 ATR% = 3.2%（P89），近一年第 89 百分位 | Binance OHLCV + 本地計算 | `EVD-001` |
| 2 | 30日實現波動率 68.4%（P92），布林帶寬 12.7%（P85） | 本地 pandas 計算 | `EVD-002` |
| 3 | 成交量 Z-score 2.4（P96），近一年第 96 百分位——顯著放量 | 本地 pandas 計算 | `EVD-003` |
| 4 | 鏈上活躍地址 7日均值 1,024,000，較30日前 +18% | mempool.space | `EVD-004` |
| 5 | Fear & Greed Index = 72（Greed），7日前為 55（Neutral） | alternative.me | `EVD-005` |
| 6 | Google News RSS 與媒體 RSS 彙整 23 則 BTC 相關報導，主要敘事偏向風險偏好回升（模擬摘要） | Google News RSS + media RSS | `EVD-006` |
| 7 | 美元指數 (DTWEXBGS) 最新 121.3，90日變化 ↑2.1% | FRED | `EVD-007` |
| 8 | 10Y 公債殖利率 4.72%，聯邦基金利率 5.33%（持平） | FRED | `EVD-008` |

### 推論層

1. **量價配合訊號**：價格突破近 20 日區間伴隨成交量 Z-score 2.4；在此模擬案例中，這組訊號定性支持短期動能增強，但未執行回測，因此不宣稱特定續漲機率。

2. **鏈上與情緒共振**：活躍地址 +18% 與情緒從 Neutral→Greed 方向一致，降低「假突破」的機率。但情緒 72 已接近過熱區（>75），需警惕短期回調。

3. **總經逆風存在但尚未兌現**：美元走強通常壓制 BTC，但目前 BTC 仍在上漲，說明加密市場內部驅動力暫時蓋過美元壓力。然而 FOMC 前市場可能轉為觀望。

### 跨來源背離偵測

⚠️ **背離訊號**：情緒指標快速升溫（55→72）的同時美元指數也在走強；兩者方向衝突，定性上提高短期回調風險。此敘述只示範跨來源推理形式，未代表已計算的歷史機率。

---

## 信心說明

**整體信心：中高（Demo 定性標示）**

### 支撐信心的因素
- 實際引用 8 筆證據，來自 6 個 canonical 獨立來源
- 價格／技術指標、鏈上、情緒等互補維度方向一致
- 技術指標百分位均由程式計算，非模型心算

### 可能推翻結論的條件
1. FOMC 會議（8月13日前後）如果釋出鷹派超預期訊號
2. CPI 數據超預期可能觸發美元進一步走強
3. 鏈上活躍度如果在下一週反轉下降（目前無此跡象）

### 已知限制
- 本次未取得衍生品數據（資金費率、未平倉合約），無法評估槓桿部位風險
- 情緒指標為全市場指數，非 BTC 專屬——引用時需注意此為代理指標
- 本 Demo 未執行歷史回測，量價與背離推論僅作定性展示，不代表已計算的未來機率

---

## 附錄

### 多維度分析摘要

- **實際分析維度**：價格、技術指標、鏈上、情緒、新聞與公告、總體經濟
- **引用證據筆數**：8
- **獨立來源數**：6
- **已知失敗嘗試**：無（此模擬案例未設定失敗工具）

#### 各維度證據與來源

- **價格**：`EVD-001`｜Binance OHLCV
- **技術指標**：`EVD-002`、`EVD-003`｜本地 pandas 計算
- **鏈上**：`EVD-004`｜mempool.space
- **情緒**：`EVD-005`｜alternative.me
- **新聞與公告**：`EVD-006`｜Google News RSS + media RSS
- **總體經濟**：`EVD-007`、`EVD-008`｜FRED

> **Demo 聲明**：以上內容與 Evidence ID 皆為介面展示用模擬資料，不代表即時市場結果。

## 附錄：完整證據清單

| Evidence ID | Source | Fetched At | Related Claim |
|-------------|--------|------------|---------------|
| EVD-001 | Binance BTCUSDT 1d | 2026-08-01T12:00:00Z | BTC 近期價格走勢與波動性評估 |
| EVD-002 | local_pandas_computation | 2026-08-01T12:00:05Z | 技術指標歷史百分位排名 |
| EVD-003 | local_pandas_computation | 2026-08-01T12:00:05Z | 成交量異常偵測 |
| EVD-004 | mempool.space | 2026-08-01T12:00:12Z | BTC 鏈上活躍度趨勢 |
| EVD-005 | alternative.me | 2026-08-01T12:00:18Z | 全市場情緒狀態 |
| EVD-006 | google-news-rss + media-rss | 2026-08-01T12:00:22Z | BTC 相關新聞與媒體敘事彙整（Demo 模擬） |
| EVD-007 | FRED (DTWEXBGS) | 2026-08-01T12:00:28Z | 美元強弱對加密市場的壓力 |
| EVD-008 | FRED (DGS10, DFF) | 2026-08-01T12:00:30Z | 利率環境對風險資產的影響 |

---

*本報告由 HOYA BIT 加密市場分析系統自動產出，僅供資訊參考，不構成投資建議。*
'''


class DemoHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT / "frontend"), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path != "/api":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        request = json.loads(body)

        print(f"[DEMO] 收到請求：symbols={request.get('symbols')}, question={request.get('question', '')[:50]}...")
        print("[DEMO] 模擬分析中（等待 3 秒）...")

        time.sleep(3)

        response = {
            "run_id": "run_20260801_demo",
            "report_text": MOCK_REPORT,
            "evidence_download_url": "#",
            "log_download_url": "#",
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))

        print("[DEMO] 已回傳模擬報告 ✓")

    def log_message(self, format, *args):
        pass


def main():
    port = 8080
    server = HTTPServer(("0.0.0.0", port), DemoHandler)
    print("=" * 60)
    print("  DEMO 展示伺服器（模擬模式，不需要任何 API 金鑰）")
    print(f"  瀏覽：http://localhost:{port}")
    print("  選個幣、打題目、按「開始分析」看效果")
    print("  Ctrl+C 停止")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
