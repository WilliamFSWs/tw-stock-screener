import yfinance as yf
import pandas as pd
from ta_utils import add_rsi, add_bbands, add_macd
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

# 股票名稱對照表 (台 50 + 中 100)
STOCK_NAMES = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2382.TW": "廣達", "2308.TW": "台達電",
    "2881.TW": "富邦金", "2882.TW": "國泰金", "2412.TW": "中華電", "3711.TW": "日月光投控", "2891.TW": "中信金",
    "2303.TW": "聯電", "2886.TW": "兆豐金", "3231.TW": "緯創", "1216.TW": "統一", "2002.TW": "中鋼",
    "5871.TW": "中租-KY", "2884.TW": "玉山金", "2892.TW": "第一金", "2357.TW": "華碩", "2345.TW": "智邦",
    "2603.TW": "長榮", "3034.TW": "聯詠", "3008.TW": "大立光", "2379.TW": "瑞昱", "2885.TW": "元大金",
    "3045.TW": "台灣大", "2880.TW": "華南金", "5880.TW": "合庫金", "2912.TW": "統一超", "2327.TW": "國巨",
    "6505.TW": "台塑化", "2301.TW": "光寶科", "4904.TW": "遠傳", "2207.TW": "和泰車", "2395.TW": "研華",
    "2890.TW": "永豐金", "2408.TW": "南亞科", "3665.TW": "貿聯-KY", "2360.TW": "致茂", "3653.TW": "健策",
    "2609.TW": "陽明", "4938.TW": "和碩", "5876.TW": "上海商銀", "2101.TW": "南港", "1301.TW": "台塑",
    "1101.TW": "台泥", "1303.TW": "南亞", "1326.TW": "台化", "2883.TW": "開發金", "2887.TW": "台新金",
    "3037.TW": "欣興", "2344.TW": "華邦電", "2449.TW": "京元電子", "2368.TW": "金像電", "3443.TW": "創意",
    "6789.TW": "采鈺", "2049.TW": "上銀", "6669.TW": "緯穎", "9910.TW": "豐泰", "1504.TW": "東元",
    "2014.TW": "中鴻", "2031.TW": "新鋼", "2356.TW": "英業達", "2352.TW": "佳世達", "2542.TW": "興富發",
    "2618.TW": "長榮航", "2610.TW": "華航", "2409.TW": "友達", "3481.TW": "群創", "1560.TW": "中砂",
    "2377.TW": "微星", "2376.TW": "技嘉", "2474.TW": "可成", "2498.TW": "宏達電", "2809.TW": "京城銀",
    "2834.TW": "臺企銀", "2838.TW": "聯邦銀", "2888.TW": "新光金", "2889.TW": "國票金", "2897.TW": "王道銀",
    "2903.TW": "遠百", "3019.TW": "亞光", "3023.TW": "信邦", "3035.TW": "智原", "3532.TW": "台勝科",
    "3533.TW": "嘉澤", "3583.TW": "辛耘", "3673.TW": "TPK-KY", "3702.TW": "大聯大", "3706.TW": "神達",
    "4919.TW": "新唐", "4958.TW": "臻鼎-KY", "5269.TW": "祥碩", "6176.TW": "瑞儀", "6213.TW": "聯茂",
    "6239.TW": "力成", "6409.TW": "旭隼", "6415.TW": "矽力*-KY", "6452.TW": "康友-KY", "6533.TW": "晶心科",
    "8046.TW": "南電", "8150.TW": "南茂", "8464.TW": "億豐", "9904.TW": "寶成", "9921.TW": "巨大",
    "9945.TW": "潤泰新", "1102.TW": "亞泥", "1402.TW": "遠東新", "1476.TW": "儒鴻", "1477.TW": "聚陽",
    "1717.TW": "長興", "1722.TW": "台肥", "1802.TW": "台玻", "1904.TW": "正隆", "2105.TW": "正新",
    "2201.TW": "裕隆", "2204.TW": "中華", "2313.TW": "華通", "2324.TW": "仁寶", "2353.TW": "宏碁",
    "2383.TW": "台光電", "2385.TW": "群光", "2404.TW": "漢唐", "2451.TW": "創見", "2606.TW": "裕民",
    "2615.TW": "萬海", "2727.TW": "王品", "2801.TW": "彰銀", "3036.TW": "文曄", "3044.TW": "健鼎",
    "8299.TW": "群聯", "5264.TW": "鎧勝-KY", "6206.TW": "飛捷", "6269.TW": "台郡", "6285.TW": "啟碁",
    "8081.TW": "致新", "3406.TW": "玉晶光", "3576.TW": "聯合再生", "3682.TW": "亞太電", "4142.TW": "國光生",
    "4906.TW": "正文", "4961.TW": "天詠", "5522.TW": "遠雄", "2439.TW": "美律", "2312.TW": "金寶",
    "2354.TW": "鴻準", "2355.TW": "敬鵬", "2363.TW": "矽統", "2371.TW": "大同", "2373.TW": "震旦行",
    "2401.TW": "凌陽", "2402.TW": "毅嘉", "2415.TW": "錩新", "2420.TW": "長興", "2421.TW": "建準",
    "2428.TW": "興勤", "2430.TW": "燦坤", "2436.TW": "偉詮電", "2441.TW": "超豐", "2457.TW": "飛宏",
    "0050.TW": "元大台灣50",
}
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
        df = add_rsi(df, length=14)
        # 2. MACD (12, 26, 9)
        df = add_macd(df, fast=12, slow=26, signal=9)
        # 3. Bollinger Bands (20, 2)
        df = add_bbands(df, length=20, std=2.0)
        
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
            name = STOCK_NAMES.get(ticker, "")
            return {
                "ticker": ticker,
                "name": name,
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
            display_name = f"{alert['name']} ({alert['ticker']})" if alert['name'] else alert['ticker']
            msg += f"{symbol} {display_name}: {alert['price']:.2f}\n"
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
