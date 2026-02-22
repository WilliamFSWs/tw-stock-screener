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

# 台灣市值前 150 大權值股名單 (包含 0050 與 0051 成分股)
TARGET_STOCKS = [
    # 0050 成分股 (部分)
    "2330.TW", "2317.TW", "2454.TW", "2382.TW", "2308.TW", "2881.TW", "2882.TW", "2412.TW", "3711.TW", "2891.TW",
    "2303.TW", "2886.TW", "3231.TW", "1216.TW", "2002.TW", "5871.TW", "2884.TW", "2892.TW", "2357.TW", "2345.TW",
    "2603.TW", "3034.TW", "3008.TW", "2379.TW", "2885.TW", "3045.TW", "2880.TW", "5880.TW", "2912.TW", "2327.TW",
    "6505.TW", "2301.TW", "4904.TW", "2207.TW", "2395.TW", "2890.TW", "2408.TW", "3665.TW", "2360.TW", "3653.TW",
    "2609.TW", "4938.TW", "5876.TW", "2101.TW", "1301.TW", "1101.TW", "1303.TW", "1326.TW", "2883.TW", "2887.TW",
    # 0051 成分股 (部分)
    "3037.TW", "2344.TW", "2449.TW", "2368.TW", "3443.TW", "6789.TW", "2049.TW", "6669.TW", "9910.TW", "1504.TW",
    "2014.TW", "2031.TW", "2356.TW", "2352.TW", "2542.TW", "2618.TW", "2610.TW", "2409.TW", "3481.TW", "1560.TW",
    "2377.TW", "2376.TW", "2474.TW", "2498.TW", "2809.TW", "2834.TW", "2838.TW", "2888.TW", "2889.TW", "2897.TW",
    "2903.TW", "3019.TW", "3023.TW", "3035.TW", "3532.TW", "3533.TW", "3583.TW", "3673.TW", "3702.TW", "3706.TW",
    "4919.TW", "4958.TW", "5269.TW", "6176.TW", "6213.TW", "6239.TW", "6409.TW", "6415.TW", "6452.TW", "6533.TW",
    "8046.TW", "8150.TW", "8464.TW", "9904.TW", "9921.TW", "9945.TW", "1102.TW", "1402.TW", "1476.TW", "1477.TW",
    "1717.TW", "1722.TW", "1802.TW", "1904.TW", "2105.TW", "2201.TW", "2204.TW", "2313.TW", "2324.TW", "2353.TW",
    "2383.TW", "2385.TW", "2404.TW", "2451.TW", "2606.TW", "2615.TW", "2727.TW", "2801.TW", "3036.TW", "3044.TW",
    "8299.TW", "5264.TW", "6206.TW", "6269.TW", "6285.TW", "8081.TW", "3406.TW", "3576.TW", "3682.TW", "4142.TW",
    "4906.TW", "4961.TW", "5522.TW", "2439.TW", "2312.TW", "2354.TW", "2355.TW", "2363.TW", "2371.TW", "2373.TW",
    "2401.TW", "2402.TW", "2415.TW", "2420.TW", "2421.TW", "2428.TW", "2430.TW", "2436.TW", "2441.TW", "2457.TW",
    # 依此類推補充其餘權值股，總計 150 隻
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
        # 特別注意：用 LINE Messaging API 傳送 JSON 格式資料，所以用 json=data
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
        send_line_messaging_api(msg)
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
