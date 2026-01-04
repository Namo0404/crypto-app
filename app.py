import streamlit as st
import requests
import ccxt
import time
from datetime import datetime

# ==========================================
# 設定エリア (Streamlitの金庫から読み込む設定)
# ==========================================
# Web上で動かす際は、キーを直接書くと危険なため、st.secretsを使います
try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
    DATABASE_ID_INPUT = st.secrets["DATABASE_ID"]
    ETH_ADDRESS = st.secrets["ETH_ADDRESS"]
    ETHERSCAN_API_KEY = st.secrets["ETHERSCAN_API_KEY"]
    
    # 取引所設定
    EXCHANGES_CONFIG = {
        'Binance': {
            'apiKey': st.secrets["BINANCE_KEY"], 
            'secret': st.secrets["BINANCE_SECRET"]
        },
        'KuCoin': {
            'apiKey': st.secrets["KUCOIN_KEY"], 
            'secret': st.secrets["KUCOIN_SECRET"], 
            'password': st.secrets["KUCOIN_PASS"]
        },
        'Coincheck': {
            'apiKey': st.secrets["COINCHECK_KEY"], 
            'secret': st.secrets["COINCHECK_SECRET"]
        },
        'Zaif': {
            'apiKey': st.secrets["ZAIF_KEY"], 
            'secret': st.secrets["ZAIF_SECRET"]
        }
    }
except Exception as e:
    st.error("APIキーの設定が見つかりません。StreamlitのSecretsを設定してください。")
    st.stop()

# ==========================================

def extract_database_id(input_string):
    if "?" in input_string: input_string = input_string.split("?")[0]
    if "/" in input_string: input_string = input_string.split("/")[-1]
    return input_string.strip()

DATABASE_ID = extract_database_id(DATABASE_ID_INPUT)

def notion_api_request(endpoint, method="POST", payload=None):
    url = f"https://api.notion.com/v1/{endpoint}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=payload)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=payload)
        return response.json()
    except Exception as e:
        return None

# --- メイン画面の構成 ---
st.title("💰 資産自動集計アプリ")
st.write("ボタンを押すと、各取引所から最新データを取得してNotionを更新します。")

if st.button('集計を開始する', type="primary"):
    
    status_text = st.empty() # 進行状況を表示するエリア
    status_text.info("🚀 処理を開始しました...")
    
    results = []

    # 1. 取引所データ取得
    for name, config in EXCHANGES_CONFIG.items():
        if not config['apiKey']: continue
        try:
            status_text.text(f"📡 {name} のデータを取得中...")
            ex_class = getattr(ccxt, name.lower())
            ex = ex_class(config)
            ex.options['adjustForTimeDifference'] = True 
            balance = ex.fetch_balance()
            
            for asset, amount in balance['total'].items():
                if amount > 0.000001 and asset != 'JPY':
                    results.append({'Asset': asset, 'Amount': amount, 'Location': name})
            
        except Exception as e:
            st.warning(f"{name} でエラーが発生: {e}")

    # 2. MEW (ETH)
    if ETH_ADDRESS:
        status_text.text(f"📡 MEW (ETH) のデータを取得中...")
        try:
            url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance&address={ETH_ADDRESS}&tag=latest&apikey={ETHERSCAN_API_KEY}"
            res = requests.get(url).json()
            if res.get('status') == '1':
                eth = int(res['result']) / 10**18
                results.append({'Asset': 'ETH', 'Amount': eth, 'Location': 'MEW'})
        except Exception as e:
            st.warning(f"MEW エラー: {e}")

    if not results:
        st.error("データが取得できませんでした。")
        st.stop()

    # 3. Notion同期
    status_text.text("🔄 価格を取得してNotionに書き込み中...")
    progress_bar = st.progress(0)
    
    # 価格取得
    assets = list(set([r['Asset'] for r in results]))
    
    # ★あなたの完全版辞書マップ
    ticker_map = {
        'BTC': 'bitcoin', 'ETH': 'ethereum', 'XRP': 'ripple', 'USDT': 'tether',
        'USDC': 'usd-coin', 'XYM': 'symbol', 'ZAIF': 'zaif', 'FLR': 'flare',
        'XEM': 'nem', 'MONA': 'monacoin', 'ETC': 'ethereum-classic',
        'BNB': 'binancecoin', 'KCS': 'kucoin-shares', 'ADA': 'cardano',
        'SOL': 'solana', 'DOT': 'polkadot', 'MATIC': 'matic-network',
        'LTC': 'litecoin', 'BCH': 'bitcoin-cash', 'XLM': 'stellar',
        'TRX': 'tron', 'EOS': 'eos', 'NEO': 'neo', 'XTZ': 'tezos',
        'VET': 'vechain', 'IOST': 'iost', 'ONT': 'ontology',
        'QTUM': 'qtum', 'BAT': 'basic-attention-token', 'ENJ': 'enjincoin'
    }
    
    cg_ids = [ticker_map.get(a, a.lower()) for a in assets]
    
    try:
        p_res = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(cg_ids)}&vs_currencies=jpy").json()
    except:
        p_res = {}

    total_jpy = 0
    
    for i, data in enumerate(results):
        key = ticker_map.get(data['Asset'], data['Asset'].lower())
        price = p_res.get(key, {}).get('jpy', 0)
        total_value = float(data['Amount']) * float(price)
        total_jpy += total_value

        # Notion検索 & 更新
        search_payload = {
            "filter": {
                "and": [
                    {"property": "Asset", "title": {"equals": data['Asset']}},
                    {"property": "Location", "select": {"equals": data['Location']}}
                ]
            }
        }
        search_res = notion_api_request(f"databases/{DATABASE_ID}/query", method="POST", payload=search_payload)

        props = {
            "Asset": {"title": [{"text": {"content": data['Asset']}}]},
            "Amount": {"number": float(data['Amount'])},
            "Location": {"select": {"name": data['Location']}},
            "Price JPY": {"number": float(price)},
            "Total Value": {"number": total_value},
            "Last Updated": {"date": {"start": datetime.now().astimezone().isoformat()}}
        }

        if search_res and search_res.get("results"):
            page_id = search_res["results"][0]["id"]
            notion_api_request(f"pages/{page_id}", method="PATCH", payload={"properties": props})
        else:
            create_payload = {"parent": {"database_id": DATABASE_ID}, "properties": props}
            notion_api_request("pages", method="POST", payload=create_payload)
        
        # プログレスバー更新
        progress_bar.progress((i + 1) / len(results))
        time.sleep(0.1)

    status_text.success("✅ 集計完了！Notionを確認してください。")
    st.metric(label="今回の総資産額", value=f"¥{int(total_jpy):,}")
    st.dataframe(results) # 取得したデータを表で表示