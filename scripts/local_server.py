"""
local_server.py — 本機開發伺服器

同時提供：
1. 靜態檔案服務（frontend/index.html）
2. API 端點（POST /api）直接呼叫 handler 邏輯

使用方式：
  cd d:\Code\GitHub Desktop\aws-hoyabit
  python scripts/local_server.py

  然後瀏覽 http://localhost:8080
"""

import json
import sys
import os
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

# 把 lambda/ 加到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lambda"))

# 載入環境變數
import config
config.load_local_env()

import handler


class LocalDevHandler(SimpleHTTPRequestHandler):
    """本機開發用的 HTTP handler。

    GET 請求：從 frontend/ 目錄提供靜態檔案
    POST /api：呼叫 lambda_handler 處理分析請求
    """

    def __init__(self, *args, **kwargs):
        # 設定靜態檔案根目錄為 frontend/
        super().__init__(*args, directory=str(PROJECT_ROOT / "frontend"), **kwargs)

    def do_OPTIONS(self):
        """處理 CORS preflight"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        """處理分析請求，直接呼叫 lambda_handler"""
        if self.path != "/api":
            self.send_error(404, "Not Found")
            return

        # 讀取 request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        # 組裝模擬的 Lambda event
        event = {"body": body}

        print(f"[API] 收到請求：{body[:200]}...")

        # 呼叫 handler
        result = handler.lambda_handler(event, None)

        # 回傳結果
        status_code = result.get("statusCode", 200)
        response_body = result.get("body", "{}")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_body.encode("utf-8"))

        print(f"[API] 回應 {status_code}")

    def log_message(self, format, *args):
        """只記錄非靜態檔案的請求，避免洗版"""
        if "GET" not in str(args[0]) or ".html" in str(args[0]):
            print(f"[SERVER] {args[0]}")


def main():
    port = 8080
    server = HTTPServer(("0.0.0.0", port), LocalDevHandler)

    print("=" * 60)
    print("  本機開發伺服器")
    print(f"  前端：http://localhost:{port}")
    print(f"  API：http://localhost:{port}/api")
    print("  Ctrl+C 停止")
    print("=" * 60)

    # 檢查必要環境變數
    missing = config.check_required_env()
    if missing:
        print(f"\n[WARN] 缺少環境變數：{', '.join(missing)}")
        print("       Agent 迴圈需要 BEDROCK_MODEL_ID 才能呼叫 Bedrock。")
        print("       請在 .env 中設定後重新啟動。\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 伺服器已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
