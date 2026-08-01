r"""
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
from urllib.parse import unquote, urlparse

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

    def do_GET(self):
        """提供前端靜態檔案，以及本機 outputs/ 交付物下載。"""
        request_path = unquote(urlparse(self.path).path)
        if not request_path.startswith("/outputs/"):
            return super().do_GET()

        outputs_root = (PROJECT_ROOT / "outputs").resolve()
        target = (outputs_root / request_path.removeprefix("/outputs/")).resolve()
        try:
            target.relative_to(outputs_root)
        except ValueError:
            self.send_error(403, "Forbidden")
            return

        if not target.is_file():
            self.send_error(404, "File not found")
            return

        content_type = "application/octet-stream"
        if target.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        elif target.suffix == ".jsonl":
            content_type = "application/x-ndjson; charset=utf-8"
        elif target.suffix == ".md":
            content_type = "text/markdown; charset=utf-8"

        payload = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

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

        # 將 storage 本機 fallback 的絕對路徑改成瀏覽器可存取的 URL。
        try:
            response_data = json.loads(response_body)
            outputs_root = (PROJECT_ROOT / "outputs").resolve()
            for field in ("evidence_download_url", "log_download_url"):
                local_value = response_data.get(field)
                if not local_value:
                    continue
                local_path = Path(local_value).resolve()
                try:
                    relative_path = local_path.relative_to(outputs_root)
                except ValueError:
                    continue
                response_data[field] = f"/outputs/{relative_path.as_posix()}"
            response_body = json.dumps(response_data, ensure_ascii=False)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            # 非 JSON 或不是本機路徑時維持 handler 原始回應。
            pass

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

    # 本機允許 DATA_BUCKET 留空，storage 會自動寫入 outputs/。
    missing = [name for name in config.check_required_env() if name != "DATA_BUCKET"]
    if missing:
        print(f"\n[WARN] 缺少環境變數：{', '.join(missing)}")
        print("       Agent 迴圈需要 BEDROCK_MODEL_ID 才能呼叫 Bedrock。")
        print("       請在 .env 中設定後重新啟動。\n")
    elif not config.DATA_BUCKET:
        print("[INFO] 本機儲存模式：交付物將寫入 outputs/，不呼叫 S3。")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 伺服器已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
