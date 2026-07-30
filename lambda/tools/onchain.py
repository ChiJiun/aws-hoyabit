"""
onchain.py — 鏈上資料工具

這是唯一需要依幣種分派到不同來源的工具，因為五個幣種是五條獨立的區塊鏈，
各自有自己的查詢介面。其他工具（價格、新聞、情緒）都是共用同一來源、
只換查詢參數。
"""


def get_onchain(symbol, metrics, lookback_days, related_claim):
    # 功能：取得指定幣種的鏈上活躍度指標。
    # 步驟：依 symbol 分派到對應的鏈上來源函式，取得指標後統一格式回傳。
    #   BTC → fetch_btc_onchain()      mempool.space
    #   ETH → fetch_evm_onchain()      Etherscan API V2
    #   BNB → fetch_evm_onchain()      Blockscout
    #   SOL → fetch_sol_onchain()      Helius
    #   XRP → fetch_xrp_onchain()      XRPL 公開節點
    # metrics 可能包含：active_addresses、tx_count、exchange_netflow 等。
    # content_reference 必須包含：實際呼叫的 API endpoint、查詢參數、
    #                            鏈上地址（若有）、資料時間範圍。
    # 回傳：統一格式 dict
    pass


def fetch_btc_onchain(metrics, lookback_days):
    # 功能：從 mempool.space 取得比特幣鏈上資料。
    # 不需要 API 金鑰。
    pass


def fetch_evm_onchain(chain, metrics, lookback_days):
    # 功能：從 EVM 相容鏈的瀏覽器 API 取得資料，ETH 與 BNB 共用這個函式。
    # chain="ethereum" → Etherscan API V2（需要金鑰）
    # chain="bsc"      → Blockscout（不需要金鑰，且 API 格式與 Etherscan 相容，
    #                    所以兩者可以共用同一套解析邏輯）
    pass


def fetch_sol_onchain(metrics, lookback_days):
    # 功能：從 Helius 取得 Solana 鏈上資料。
    # 注意：不要用 Solscan 官方 API，該服務已改為付費方案。
    pass


def fetch_xrp_onchain(metrics, lookback_days):
    # 功能：從 XRPL 公開節點取得 XRP 帳本資料。
    # 標準 JSON-RPC 介面，不需要 API 金鑰。
    pass