#!/bin/bash
# package_lambda.sh — 把 lambda/ 資料夾打包成可以上傳到 AWS Lambda 的 zip
#
# 用法：在專案根目錄執行 ./scripts/package_lambda.sh
#
# 注意：pandas / numpy 體積較大，若打包後超過 Lambda 的大小限制，
#      改用 Lambda Layer 或容器映像部署，這支腳本只適合先求能動的最小版本。

set -e   # 任何一步出錯就整支腳本停止，避免打包出一個壞掉的 zip

cd "$(dirname "$0")/.."   # 確保無論從哪裡執行，都會回到專案根目錄

rm -rf build function.zip
mkdir build

# 複製程式碼本體
cp -r lambda/. build/

# 把依賴套件一起安裝進 build 資料夾（Lambda 執行環境不會自動幫你裝）
pip install -r requirements.txt -t build --break-system-packages --quiet

# 壓成 zip
cd build
zip -r ../function.zip . -x "*.pyc" "__pycache__/*" > /dev/null
cd ..

rm -rf build

echo "打包完成：function.zip"
echo "上傳指令："
echo "  aws lambda update-function-code --function-name 你的function名稱 --zip-file fileb://function.zip"