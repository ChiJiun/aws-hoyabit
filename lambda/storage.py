"""
storage.py — S3 讀寫與下載連結

所有跟 S3 互動的操作集中在這裡。本機測試時可以讓這些函式改讀寫本地檔案，
這樣同一份程式碼在本機與 Lambda 上都能跑。
"""


def read_baseline_csv(symbol):
    # 功能：從 S3 讀取指定幣種的賽方基準 OHLCV CSV。
    # 路徑：s3://{DATA_BUCKET}/baseline/{symbol}USDT_daily_ohlcv.csv
    # 實作：boto3 s3_client.get_object() 取得檔案內容，用 pandas.read_csv 解析。
    # 回傳：pandas DataFrame（欄位：date, open, high, low, close, volume）
    pass


def save_raw_payload(run_id, evidence_id, raw_data):
    # 功能：把單次外部 API 呼叫的原始回應封存到 S3，供主辦方抽查回溯。
    # 路徑：s3://{DATA_BUCKET}/runs/{run_id}/raw/{evidence_id}.json
    # 實作：json.dumps 後用 s3_client.put_object() 上傳。
    # 回傳：該檔案的 S3 URI 字串
    pass


def save_output_file(run_id, filename, content):
    # 功能：把最終交付物（報告、證據清單、執行紀錄）上傳到 S3。
    # 路徑：s3://{DATA_BUCKET}/runs/{run_id}/{filename}
    # 實作：s3_client.put_object()。
    # 回傳：該檔案的 S3 key
    pass


def generate_download_link(key, expires_in=3600):
    # 功能：為 S3 上的檔案產生有時效性的下載連結（presigned URL）。
    #      這樣資料 bucket 不必設為公開，評審也能點連結下載交付物。
    # 實作：s3_client.generate_presigned_url("get_object", Params={...}, ExpiresIn=expires_in)
    # 回傳：可直接放在網頁上的 https 網址字串
    pass