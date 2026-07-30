#!/bin/bash
# upload_baseline.sh — 把賽方提供的基準 CSV 上傳到資料 bucket
#
# 用法：在專案根目錄執行 ./scripts/upload_baseline.sh 你的資料bucket名稱
#
# 只需要在拿到賽方資料時執行一次；之後 Lambda 都是直接讀 S3 上的版本，
# 不會每次執行都重新上傳。

set -e

BUCKET="$1"

if [ -z "$BUCKET" ]; then
  echo "用法：./scripts/upload_baseline.sh 你的資料bucket名稱"
  exit 1
fi

cd "$(dirname "$0")/.."

aws s3 sync data/baseline/ "s3://${BUCKET}/baseline/" \
  --exclude ".gitkeep"

echo "已上傳基準資料至 s3://${BUCKET}/baseline/"
aws s3 ls "s3://${BUCKET}/baseline/"