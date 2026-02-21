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


load_dotenv()

# Parameters
LINE_NOTIFY_TOKEN = os.getenv("LINE_TOKEN", "")

TARGET_STOCKS = [
      "2330.TW",
      "2317.TW",
      "2454.TW",
      "2382.TW",
      "2308.TW",
      "2881.TW",
      "2882.TW",
      "2412.TW",
      "3711.TW",
      "2891.TW",
      "2303.TW",
      "2886.TW",
      "3231.TW",
      "1216.TW",
      "2002.TW",
      "5871.TW",
      "2884.TW",
      "2892.TW",
      "2357.TW",
      "2345.TW",
      "0050.TW",
]

def send_line_notify(message):
      if not LINE_NOTIFY_TOKEN:
                print("LINE_NOTIFY_TOKEN not set")
                return

      url = 'https://notify-api.line.me/api/notify'
      headers = {
          'Authorization': f'Bearer {LINE_NOTIFY_TOKEN}'
      }
      data = {
          'message': message
      }

    proxies = {}
    http_proxy = os.getenv("HTTP_PROXY", "")
    https_proxy = os.getenv("HTTPS_PROXY", "")
    if http_proxy:
              proxies['http'] = http_proxy
          if https_proxy:
                    proxies['https'] = https_proxy

    try:
              response = requests.post(url, headers=headers, data=data, proxies=proxies if proxies else None)
              if response.status_code == 200:
                            print("Line success")
    else:
            print(f"Line fail: {response.status_code}, {response.text}")
except Exception as e:
        print(f"Line error: {e}")

def check_stock_signals(ticker):
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
                      reasons.append(f"RSI Oversold ({rsi:.1f})")
                      signal = "STRONG BUY"
elif close_price < bb_lower and rsi < 40:
            reasons.append(f"Below BB Lower and RSI low ({rsi:.1f})")
            signal = "STRONG BUY"

        if rsi > 75:
                      reasons.append(f"RSI Overbought ({rsi:.1f})")
                      signal = "STRONG SELL"
elif close_price > bb_upper and rsi > 60:
            reasons.append(f"Above BB Upper and RSI high ({rsi:.1f})")
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
        print(f"Error {ticker}: {e}")
        return None

def job(force=False):
      tz = pytz.timezone('Asia/Taipei')
    now = datetime.datetime.now(tz)

    if not force:
              if now.weekday() >= 5:
                            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Weekend, skip.")
                            return

              current_time = now.time()
              start_time = datetime.time(9, 0)
              end_time = datetime.time(13, 45)

        if not (start_time <= current_time <= end_time):
                      print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Closed, skip.")
                      return

    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] Scanning stocks...")

    alerts = []
    for ticker in TARGET_STOCKS:
              result = check_stock_signals(ticker)
              if result:
                            alerts.append(result)
                        time.sleep(0.5)

    if alerts:
              msg = f"\n Stock Signals ({now.strftime('%H:%M')})\n"
        msg += "-" * 20 + "\n"
        for alert in alerts:
                      symbol = "GREEN" if alert["signal"] == "STRONG BUY" else "RED"
                      msg += f"{symbol} {alert['ticker']}: {alert['price']:.2f}\n"
                      msg += f" -> Reasons: {', '.join(alert['reasons'])}\n"

        print(msg)
        send_line_notify(msg)
else:
        print("No signals.")

if __name__ == "__main__":
      tz = pytz.timezone('Asia/Taipei')
    print(f"System started - {datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}")

    if os.getenv("RUN_ONCE") == "true":
              job(force=True)
else:
        job(force=True)

        schedule.every().day.at("09:30").do(job)
        schedule.every().day.at("10:30").do(job)
        schedule.every().day.at("11:30").do(job)
        schedule.every().day.at("12:30").do(job)
        schedule.every().day.at("13:30").do(job)

        while True:
                      schedule.run_pending()
                      time.sleep(60)
          
