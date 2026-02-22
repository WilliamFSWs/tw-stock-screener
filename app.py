import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import datetime
import pytz
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_USER_ID = os.getenv("LINE_USER_ID")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

STOCK_NAMES = {
          "2330.TW": "TSMC", "2317.TW": "Hon Hai", "2454.TW": "MediaTek", "2382.TW": "Quanta", "2308.TW": "Delta",
          "2881.TW": "Fubon", "2882.TW": "Cathay", "2412.TW": "Chunghwa", "3711.TW": "ASE", "2891.TW": "CTBC",
          "2303.TW": "UMC", "2886.TW": "Mega", "3231.TW": "Wistron", "1216.TW": "Uni-President", "2002.TW": "CSC",
          "5871.TW": "Chailease", "2884.TW": "E.SUN", "2892.TW": "First", "2357.TW": "ASUS", "2345.TW": "Accton",
          "2603.TW": "Evergreen", "3034.TW": "Novatek", "3008.TW": "Largan", "2379.TW": "Realtek", "2885.TW": "Yuanta",
          "3045.TW": "Taiwan Mobile", "2880.TW": "Huanan", "5880.TW": "Taiwan Cooperative", "2912.TW": "PCSC", "2327.TW": "Yageo",
          "6505.TW": "FPCC", "2301.TW": "Lite-On", "4904.TW": "FarEasTone", "2207.TW": "Hotai", "2395.TW": "Advantech",
          "2890.TW": "SinoPac", "2408.TW": "Nanya Tech", "3665.TW": "BizLink", "2360.TW": "Chroma", "3653.TW": "Jentech",
          "2609.TW": "Yang Ming", "4938.TW": "Pegatron", "5876.TW": "Shanghai Bank", "2101.TW": "Nankang", "1301.TW": "FPC",
          "1101.TW": "TCC", "1303.TW": "NPC", "1326.TW": "FCFC", "2883.TW": "CDF", "2887.TW": "Taishin",
          "3037.TW": "Unimicron", "2344.TW": "Winbond", "2449.TW": "KYEC", "2368.TW": "Gold Circuit", "3443.TW": "GUC",
          "6789.TW": "VisEra", "2049.TW": "HIWIN", "6669.TW": "Wiwynn", "9910.TW": "Feng Tay", "1504.TW": "TECO",
          "2014.TW": "Chung Hung", "2031.TW": "Sheng Yu", "2356.TW": "Inventec", "2352.TW": "Qisda", "2542.TW": "Highwealth",
          "2618.TW": "EVA Air", "2610.TW": "China Airlines", "2409.TW": "AUO", "3481.TW": "Innolux", "1560.TW": "Kinik",
          "2377.TW": "MSI", "2376.TW": "GIGABYTE", "2474.TW": "Catcher", "2498.TW": "HTC", "2809.TW": "KCB",
          "2834.TW": "TBB", "2838.TW": "Union Bank", "2888.TW": "Shin Kong", "2889.TW": "IBF", "2897.TW": "O-Bank",
          "2903.TW": "Far Eastern", "3019.TW": "Asia Optical", "3023.TW": "Sinbon", "3035.TW": "Faraday", "3532.TW": "GWC",
          "3533.TW": "Chicony Power", "3583.TW": "Scientech", "3673.TW": "TPK", "3702.TW": "WPG", "3706.TW": "MiTAC",
}
def analyze_stock(ticker):
          if ticker.isdigit():
                        ticker += ".TW"
                    try:
                                  stock = yf.Ticker(ticker)
                                  df = stock.history(period="6mo")
                                  if df.empty or len(df) < 50:
                                                    return f"Error: Cannot find stock '{ticker}'"
                                                df.ta.rsi(length=14, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        latest = df.iloc[-1]
        close_p = latest['Close']
        rsi_val = latest['RSI_14']
        bb_u = latest['BBU_20_2.0_2.0']
        bb_l = latest['BBL_20_2.0_2.0']
        name = STOCK_NAMES.get(ticker, "Unknown")
        trend = "Neutral"
        if rsi_val > 70: trend = "Overbought (Sell)"
elif rsi_val < 30: trend = "Oversold (Buy)"
elif close_p > bb_u: trend = "Above BB Upper"
elif close_p < bb_l: trend = "Below BB Lower"
        msg = f"Stock: {name} ({ticker})\n"
        msg += f"Price: {close_p:.2f}\nRSI: {rsi_val:.2f}\n"
        msg += f"BB: {bb_l:.2f} - {bb_u:.2f}\n"
        msg += f"Advice: {trend}"
        return msg
except Exception as e:
        return f"Error: {str(e)}"
@app.route("/callback", methods=['POST'])
def callback():
          signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
                  handler.handle(body, signature)
except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
          user_text = event.message.text.strip().upper()
    if user_text.isdigit() or (".TW" in user_text):
                  result = analyze_stock(user_text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result))
else:
        line_bot_api.reply_message(
            event.reply_token, 
                          TextSendMessage(text="Hello! Send a stock code (e.g. 2330) for diagnosis.")
        )

if __name__ == "__main__":
          port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
