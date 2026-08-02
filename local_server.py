"""
local_server.py — 本地 Demo 用 HTTP Server

同時 serve 前端靜態檔案和後端 API，模擬完整的部署環境。
執行：python local_server.py
瀏覽器打開：http://localhost:8080
"""

import json
import sys
import os
import re
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

# 確保 lambda 目錄在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent / "lambda"))

import config  # noqa: E402
config.load_local_env()

import handler  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
PORT = 8080


def _rewrite_file_urls(resp_body):
    """把回應中的 file:// 本機路徑轉換為 /outputs/ HTTP URL。"""
    try:
        data = json.loads(resp_body)
    except Exception:
        return resp_body

    outputs_str = str(OUTPUTS_DIR).replace("\\", "/")

    for key in ("evidence_download_url", "log_download_url"):
        val = data.get(key, "")
        if not val:
            continue
        # 處理 file:///path 或直接的絕對路徑
        normalized = val.replace("\\", "/")
        if normalized.startswith("file:///"):
            normalized = normalized[len("file:///"):]
        # 把絕對路徑轉成相對 /outputs/ URL
        if outputs_str.lstrip("/") in normalized or normalized.startswith(outputs_str):
            relative = normalized.split("outputs/", 1)[-1] if "outputs/" in normalized else ""
            if relative:
                data[key] = f"/outputs/{relative}"

    return json.dumps(data, ensure_ascii=False)


class DemoHandler(SimpleHTTPRequestHandler):
    """同時處理前端靜態檔案、/outputs/ 下載、和 /api POST 請求。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self):
        """處理 GET — /outputs/ 路徑從 outputs 目錄讀取，其餘從 frontend。"""
        if self.path.startswith("/outputs/"):
            # Serve from outputs directory
            relative = unquote(self.path[len("/outputs/"):])
            file_path = OUTPUTS_DIR / relative
            if file_path.is_file():
                self.send_response(200)
                # 設定 Content-Type
                if file_path.suffix == ".json":
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                elif file_path.suffix == ".jsonl":
                    self.send_header("Content-Type", "application/jsonl; charset=utf-8")
                elif file_path.suffix == ".md":
                    self.send_header("Content-Type", "text/markdown; charset=utf-8")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Access-Control-Allow-Origin", "*")
                content = file_path.read_bytes()
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, f"File not found: {relative}")
            return
        # 其他路徑走前端
        super().do_GET()

    def do_OPTIONS(self):
        """處理 CORS preflight。"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        """處理 /api POST — 呼叫 lambda_handler。"""
        if self.path != "/api":
            self.send_error(404)
            return

        # 讀取 request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        # 組裝成 Lambda event 格式
        event = {"body": body}

        print(f"\n[API] 收到請求：{body[:200]}...")

        # 呼叫 handler
        try:
            response = handler.lambda_handler(event, None)
        except Exception as e:
            response = {
                "statusCode": 500,
                "headers": {"Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": str(e)}),
            }

        # 把 file:// URL 轉成 HTTP /outputs/ URL
        status = response.get("statusCode", 200)
        resp_body = response.get("body", "")
        if status == 200:
            resp_body = _rewrite_file_urls(resp_body)

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(resp_body.encode("utf-8"))

        # 印出摘要
        try:
            parsed = json.loads(resp_body)
            if "report_text" in parsed:
                print(f"[API] 完成！報告長度 {len(parsed['report_text'])} 字元")
            elif "error" in parsed:
                print(f"[API] 錯誤：{parsed['error']}")
        except Exception:
            pass


def main():
    print("=" * 60)
    print("加密市場分析 AI Agent — 本地 Demo Server")
    print(f"前端目錄：{FRONTEND_DIR}")
    print(f"啟動於：http://localhost:{PORT}")
    print("按 Ctrl+C 停止")
    print("=" * 60)

    # 用多執行緒：分析可能耗時數十秒，期間瀏覽器仍需能載入其他資源
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DemoHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Server 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
