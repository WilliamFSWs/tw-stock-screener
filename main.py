import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import schedule
import time
import datetime
import pytz
import os
from dotenv import load_dotenv

# 讀取 .env 檔案中的環境變數
load_dotenv()

# ==========================================
# 參數設定
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "") 
LINE_USER_ID = os.getenv("LINE_USER_ID", "") 

# 台灣主要權值股名單 (為避免執行過久，初步篩選前 20 大權值股)
TARGET_STOCKS = [
    "2330.TW", # 台積電
    "2317.TW", # 鴻海
    "2454.TW", # 聯發科
    "2382.TW", # 廣達
    "2308.TW", # 台達電
    "2881.TW", # 富邦金
    "2882.TW", # 國泰金
    "2412.TW", # 中華電
    "3711.TW", # 日月光投控
    "2891.TW", # 中信金
    "2303.TW", # 聯電
    "2886.TW", # 兆豐金
    "3231.TW", # 緯創
    "1216.TW", # 統一
    "2002.TW", # 中鋼
    "5871.TW", # 中租-KY
    "2884.TW", # 玉山金
    "2892.TW", # 第一金
    "2357.TW", # 華碩
    "2345.TW", # 智邦
    "0050.TW", # 元大台灣50 (大盤參考)
]

def send_line_messaging_api(message):
    """發送 LINE Messaging API 推播訊息"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("[警告] 尚未設定 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_ID，跳過推播。")
        return
        
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
    }
    data = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    
    # 讀取代理伺服器設定 (若是 GitHub Actions 雲端環境則不要使用 proxy)
    proxies = {}
    if os.getenv("RUN_ONCE") != "true":
        http_proxy = os.getenv("HTTP_PROXY", "")
        https_proxy = os.getenv("HTTPS_PROXY", "")
        if http_proxy:
            proxies['http'] = http_proxy
        if https_proxy:
            proxies['https'] = https_proxy
            
    try:
        response = requests.post(url, headers=headers, json=data, proxies=proxies if proxies else None)
        if response.status_code == 200:
            print("Line Webhook 推播發送成功")
        else:
            print(f"Line Webhook 推播發送失敗: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"發送 Line Webhook 時發生錯誤: {e}")

def check_stock_signals(ticker):
    """取得股票資料並計算技術指標，判斷買賣訊號"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        
        if df.empty or len(df) < 50:
            return None
            
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        
        latest = df.iloc[-1]
        
        if pd.isna(latest['RSI_14']) or pd.isna(latest['BBL_20_2.0_2.0']) or pd.isna(latest['MACDh_12_26_9']):
            return None

        rsi = latest['RSI_14']
        close_price = latest['Close']
        bb_lower = latest['BBL_20_2.0_2.0']
        bb_upper = latest['BBU_20_2.0_2.0']
        macd_hist = latest['MACDh_12_26_9']
        
        signal = None
        reasons = []

        if rsi < 25:
            reasons.append(f"RSI 超賣 ({rsi:.1f})")
            signal = "STRONG BUY"
        elif close_price < bb_lower and rsi < 40:
            reasons.append(f"跌破布林下軌且 RSI 偏低 ({rsi:.1f})")
            signal = "STRONG BUY"

        if rsi > 75:
            reasons.append(f"RSI 超買 ({rsi:.1f})")
            signal = "STRONG SELL"
        elif close_price > bb_upper and rsi > 60:
            reasons.append(f"突破布林上軌且 RSI 偏高 ({rsi:.1f})")
            signal = "STRONG SELL"
            
        if signal:
            return {
                "ticker": ticker,
                "price": close_price,
                "signal": signal,
                "reasons": reasons,
                "rsi": rsi,
                "macd_h": macd_hist
            }
        return None
        
    except Exception as e:
        print(f"處理 {ticker} 時發生錯誤: {e}")
        return None

def job(force=False):
    """定時排程執行的任務"""
    tz = pytz.timezone('Asia/Taipei')
    now = datetime.datetime.now(tz)
    
    if not force:
        if now.weekday() >= 5:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 週休二日，不執行掃描。")
            return
            
        current_time = now.time()
        start_time = datetime.time(9, 0)
        end_time = datetime.time(13, 45)
        
        if not (start_time <= current_time <= end_time):
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 非開盤時間，跳過。")
            return

    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 開始執行台股技術訊號掃描...")
    
    alerts = []
    for ticker in TARGET_STOCKS:
        result = check_stock_signals(ticker)
        if result:
            alerts.append(result)
            time.sleep(0.5)
            
    if alerts:
        msg = f"\n📊 台股強烈買賣訊號特報 ({now.strftime('%H:%M')})\n"
        msg += "-" * 20 + "\n"
        for alert in alerts:
            symbol = "🟢" if alert["signal"] == "STRONG BUY" else "🔴"
            msg += f"{symbol} {alert['ticker']}: {alert['price']:.2f}\n"
            msg += f"   ➤ 理由: {', '.join(alert['reasons'])}\n"
        
        print("\n發送推播訊息:")
        print(msg)
        send_line_messaging_api(msg)
    else:
        print("本次掃描無強烈訊號。")

if __name__ == "__main__":
    tz = pytz.timezone('Asia/Taipei')
    print(f"啟動台股技術線型篩選系統 - 現在時間: {datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}")
    
    if os.getenv("RUN_ONCE") == "true":
        print("執行模式: 單次執行 (RUN_ONCE)")
        job(force=True)
    else:
        job(force=True)
        
        schedule.every().day.at("09:30").do(job)
        schedule.every().day.at("10:30").do(job)
        schedule.every().day.at("11:30").do(job)
        schedule.every().day.at("12:30").do(job)
        schedule.every().day.at("13:30").do(job)
        
        print("排程已設定。按下 Ctrl+C 結束。")
        
        while True:
            schedule.run_pending()
            time.sleep(60)
