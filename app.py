import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from main import check_stock_signals, TARGET_STOCKS, send_line_messaging_api

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_USER_ID = os.getenv('LINE_USER_ID')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

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
      msg = event.message.text.strip().lower()
      if msg in ["scan", "run", "start"]:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="Scanning..."))
                try:
                              signals = check_stock_signals(TARGET_STOCKS)
                              if signals:
                                                send_line_messaging_api(signals)
                else:
                                  line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text="No signals."))
                except Exception as e:
                    line_bot_api.push_message(LINE_USER_ID, TextSendMessage(text=f"Error: {str(e)}"))
elif msg in ["list", "stocks"]:
        sample = list(TARGET_STOCKS.keys())[:10]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"Monitoring {len(TARGET_STOCKS)} stocks: {', '.join(sample)}"))
else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="Commands: scan, list"))

if __name__ == "__main__":
      port = int(os.environ.get('PORT', 8080))
      app.run(host='0.0.0.0', port=port)
