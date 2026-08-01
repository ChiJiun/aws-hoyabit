#!/bin/bash
# set_api_url.sh — 部署後替換 frontend/index.html 中的 API_URL 為真實的 Lambda Function URL
#
# 用法：./scripts/set_api_url.sh https://abc123xyz.lambda-url.us-east-1.on.aws/
#
# 此腳本會：
#   1. 驗證傳入的 URL 格式（必須含 .lambda-url. 且以 .on.aws/ 結尾）
#   2. 用 sed 替換 index.html 中的 API_URL 常數值
#   3. 印出確認訊息

set -e

cd "$(dirname "$0")/.."   # 回到專案根目錄

FRONTEND_FILE="frontend/index.html"

# 檢查參數
if [ -z "$1" ]; then
  echo "錯誤：請提供 Lambda Function URL"
  echo "用法：./scripts/set_api_url.sh https://your-id.lambda-url.us-east-1.on.aws/"
  exit 1
fi

FUNCTION_URL="$1"

# 驗證 URL 格式
if [[ ! "$FUNCTION_URL" =~ \.lambda-url\. ]] || [[ ! "$FUNCTION_URL" =~ \.on\.aws/$ ]]; then
  echo "錯誤：URL 格式不正確"
  echo "預期格式：https://<id>.lambda-url.<region>.on.aws/"
  echo "收到的值：$FUNCTION_URL"
  exit 1
fi

# 檢查前端檔案存在
if [ ! -f "$FRONTEND_FILE" ]; then
  echo "錯誤：找不到 $FRONTEND_FILE"
  exit 1
fi

# 替換 API_URL（匹配 const API_URL = "..."; 這一行）
sed -i "s|const API_URL = \".*\";|const API_URL = \"${FUNCTION_URL}\";|" "$FRONTEND_FILE"

# 確認替換結果
CURRENT_URL=$(grep 'const API_URL' "$FRONTEND_FILE" | sed 's/.*"\(.*\)".*/\1/')

echo "完成：API_URL 已更新"
echo "  檔案：$FRONTEND_FILE"
echo "  URL ：$CURRENT_URL"
