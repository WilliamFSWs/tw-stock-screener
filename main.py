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
LINE_NOTIFY_TOKEN = os.getenv("LINE_TOKEN", "") # 請在 .env 檔案中設定 LINE_TOKEN=您的權杖

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

def send_line_notify(message):
    """發送 Line Notify 訊息"""
    if not LINE_NOTIFY_TOKEN:
        print("[警告] 尚未設定 LINE_NOTIFY_TOKEN，跳過推播。")
        return
        
    url = 'https://notify-api.line.me/api/notify'
    headers = {
        'Authorization': f'Bearer {LINE_NOTIFY_TOKEN}'
    }
    data = {
        'message': message
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
        response = requests.post(url, headers=headers, data=data, proxies=proxies if proxies else None)
        if response.status_code == 200:
            print("Line 通知發送成功")
        else:
            print(f"Line 通知發送失敗: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"發送 Line 通知時發生錯誤: {e}")

def check_stock_signals(ticker):
    """取得股票資料並計算技術指標，判斷買賣訊號"""
    try:
        # 抓取過去 6 個月的日線資料 (以確保能算百日均線等)，這裡抓 daily 代表當日收盤/即時盤
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        
        if df.empty or len(df) < 50:
            return None
            
        # 計算技術指標
        # 1. RSI (14)
        df.ta.rsi(length=14, append=True)
        # 2. MACD (12, 26, 9)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        # 3. Bollinger Bands (20, 2)
        df.ta.bbands(length=20, std=2, append=True)
        
        # 取得最後一筆資料 (即時股價或最新收盤價)
        latest = df.iloc[-1]
        
        # 處理缺失值
        if pd.isna(latest['RSI_14']) or pd.isna(latest['BBL_20_2.0_2.0']) or pd.isna(latest['MACDh_12_26_9']):
            return None

        rsi = latest['RSI_14']
        close_price = latest['Close']
        bb_lower = latest['BBL_20_2.0_2.0']
        bb_upper = latest['BBU_20_2.0_2.0']
        macd_hist = latest['MACDh_12_26_9']
        
        signal = None
        reasons = []

        # -- 強烈買進條件判定 --
        # 條件 1: RSI 嚴重超賣 (< 25)
        if rsi < 25:
            reasons.append(f"RSI 超賣 ({rsi:.1f})")
            signal = "STRONG BUY"
            
        # 條件 2: 股價跌破布林通道下軌 且 RSI 在低檔 (< 40)
        elif close_price < bb_lower and rsi < 40:
            reasons.append(f"跌破布林下軌且 RSI 偏低 ({rsi:.1f})")
            signal = "STRONG BUY"

        # -- 強烈賣出條件判定 --
        # 條件 1: RSI 嚴重超買 (> 75)
        if rsi > 75:
            reasons.append(f"RSI 超買 ({rsi:.1f})")
            signal = "STRONG SELL"
            
        # 條件 2: 股價突破布林通道上軌 且 RSI 高檔 (> 60)
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
    
    # 若非強制執行，則檢查是否在開盤時間
    if not force:
        # 判斷是否為週末 (0=星期一, 6=星期日)
        if now.weekday() >= 5:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 週休二日，不執行掃描。")
            return
            
        # 判斷是否在開盤時間 09:00 - 13:30 之間 (加一點寬容至 13:45)
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
            # 避免 API 請求過於頻繁
            time.sleep(0.5)
            
    if alerts:
        # 組合推播訊息
        msg = f"\n📊 台股強烈買賣訊號特報 ({now.strftime('%H:%M')})\n"
        msg += "-" * 20 + "\n"
        for alert in alerts:
            symbol = "🟢" if alert["signal"] == "STRONG BUY" else "🔴"
            msg += f"{symbol} {alert['ticker']}: {alert['price']:.2f}\n"
            msg += f"   ➤ 理由: {', '.join(alert['reasons'])}\n"
        
        print("\n發送推播訊息:")
        print(msg)
        send_line_notify(msg)
    else:
        print("本次掃描無強烈訊號。")

if __name__ == "__main__":
    tz = pytz.timezone('Asia/Taipei')
    print(f"啟動台股技術線型篩選系統 - 現在時間: {datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 支援單次執行模式 (用於 GitHub Actions)
    if os.getenv("RUN_ONCE") == "true":
        print("執行模式: 單次執行 (RUN_ONCE)")
        job(force=True)
    else:
        # 啟動時先強制執行一次測試
        job(force=True)
        
        # 設定排程: 每天的 9:30, 10:30, 11:30, 12:30, 13:30 執行
        schedule.every().day.at("09:30").do(job)
        schedule.every().day.at("10:30").do(job)
        schedule.every().day.at("11:30").do(job)
        schedule.every().day.at("12:30").do(job)
        schedule.every().day.at("13:30").do(job)
        
        print("排程已設定。按下 Ctrl+C 結束。")
        
        while True:
            schedule.run_pending()
            time.sleep(60)
