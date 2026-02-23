import os
import yfinance as yf
import pandas as pd
from ta_utils import add_rsi, add_bbands
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv
from pv_pattern_backtest import add_features, calculate_win_rate_score

load_dotenv()

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_USER_ID = os.getenv("LINE_USER_ID")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

STOCK_NAMES = {'2330.TW': '\u53f0\u7a4d\u96fb', '2317.TW': '\u9d3b\u6d77', '2454.TW': '\u806f\u767c\u79d1', '2382.TW': '\u5ee3\u9054', '2308.TW': '\u53f0\u9054\u96fb', '2881.TW': '\u5bcc\u90a6\u91d1', '2882.TW': '\u570b\u6cf0\u91d1', '2412.TW': '\u4e2d\u83ef\u96fb', '3711.TW': '\u65e5\u6708\u5149\u6295\u63a7', '2891.TW': '\u4e2d\u4fe1\u91d1', '2303.TW': '\u806f\u96fb', '2886.TW': '\u5146\u8c4a\u91d1', '3231.TW': '\u7def\u5275', '1216.TW': '\u7d71\u4e00', '2002.TW': '\u4e2d\u92fc', '5871.TW': '\u4e2d\u79df-KY', '2884.TW': '\u7389\u5c71\u91d1', '2892.TW': '\u7b2c\u4e00\u91d1', '2357.TW': '\u83ef\u78a9', '2345.TW': '\u667a\u90a6', '2603.TW': '\u9577\u69ae', '3034.TW': '\u806f\u8a60', '3008.TW': '\u5927\u7acb\u5149', '2379.TW': '\u745e\u6631', '2885.TW': '\u5143\u5927\u91d1', '3045.TW': '\u53f0\u7063\u5927', '2880.TW': '\u83ef\u5357\u91d1', '5880.TW': '\u5408\u5eab\u91d1', '2912.TW': '\u7d71\u4e00\u8d85', '2327.TW': '\u570b\u5de8', '6505.TW': '\u53f0\u5851\u5316', '2301.TW': '\u5149\u5bf6\u79d1', '4904.TW': '\u9060\u50b3', '2207.TW': '\u548c\u6cf0\u8eca', '2395.TW': '\u7814\u83ef', '2890.TW': '\u6c38\u8c50\u91d1', '2408.TW': '\u5357\u4e9e\u79d1', '3665.TW': '\u8cbf\u806f-KY', '2360.TW': '\u81f4\u8302', '3653.TW': '\u5065\u7b56', '2609.TW': '\u967d\u660e', '4938.TW': '\u548c\u78a9', '5876.TW': '\u4e0a\u6d77\u5546\u9280', '2101.TW': '\u5357\u6e2f', '1301.TW': '\u53f0\u5851', '1101.TW': '\u53f0\u6ce5', '1303.TW': '\u5357\u4e9e', '1326.TW': '\u53f0\u5316', '2883.TW': '\u958b\u767c\u91d1', '2887.TW': '\u53f0\u65b0\u91d1', '3037.TW': '\u6b23\u8208', '2344.TW': '\u83ef\u90a6\u96fb', '2449.TW': '\u4eac\u5143\u96fb\u5b50', '2368.TW': '\u91d1\u50cf\u96fb', '3443.TW': '\u5275\u610f', '6789.TW': '\u91c7\u923a', '2049.TW': '\u4e0a\u9280', '6669.TW': '\u7def\u7a4e', '9910.TW': '\u8c50\u6cf0', '1504.TW': '\u6771\u5143', '2014.TW': '\u4e2d\u9d3b', '2031.TW': '\u65b0\u92fc', '2356.TW': '\u82f1\u696d\u9054', '2352.TW': '\u4f73\u4e16\u9054', '2542.TW': '\u8208\u5bcc\u767c', '2618.TW': '\u9577\u69ae\u822a', '2610.TW': '\u83ef\u822a', '2409.TW': '\u53cb\u9054', '3481.TW': '\u7fa4\u5275', '1560.TW': '\u4e2d\u7802', '2377.TW': '\u5fae\u661f', '2376.TW': '\u6280\u5609', '2474.TW': '\u53ef\u6210', '2498.TW': '\u5b4f\u9054\u96fb', '2809.TW': '\u4eac\u57ce\u9280', '2834.TW': '\u81fa\u4f01\u9280', '2838.TW': '\u806f\u90a6\u9280', '2888.TW': '\u65b0\u5149\u91d1', '2889.TW': '\u570b\u7968\u91d1', '2897.TW': '\u738b\u9054\u91d1', '2903.TW': '\u9060\u767e', '3019.TW': '\u4e9e\u5149', '3023.TW': '\u4fe1\u90a6', '3035.TW': '\u667a\u539f', '3532.TW': '\u53f0\u52dd\u79d1', '3533.TW': '\u5609\u6fa4', '3583.TW': '\u8f9b\u9210', '3673.TW': 'TPK-KY', '3702.TW': '\u5927\u806f\u5927', '3706.TW': '\u795e\u9054', '4919.TW': '\u65b0\u5510', '4958.TW': '\u81fb\u9f0e-KY', '5269.TW': '\u7965\u78a9', '6176.TW': '\u745e\u5110', '6213.TW': '\u806f\u8302', '6239.TW': '\u529b\u6210', '6409.TW': '\u65ed\u96bc', '6415.TW': '\u77fd\u524b*-KY', '6452.TW': '\u5eb7\u53cb-KY', '6533.TW': '\u667a\u5fc3\u79d1', '8046.TW': '\u5357\u96fb', '8150.TW': '\u5357\u8302', '8464.TW': '\u5104\u8c50', '9904.TW': '\u5bf6\u6210', '9921.TW': '\u5de8\u5927', '9945.TW': '\u6f64\u6cf0\u65b0', '1102.TW': '\u4e9e\u6ce5', '1402.TW': '\u9060\u6771\u65b0', '1476.TW': '\u5112\u9d3b', '1477.TW': '\u805a\u967d', '1717.TW': '\u9577\u8208', '1722.TW': '\u53f0\u80a5', '1802.TW': '\u53f0\u73bb', '1904.TW': '\u6b63\u9686', '2105.TW': '\u6b63\u65b0', '2201.TW': '\u88d5\u9686', '2204.TW': '\u4e2d\u83ef', '2313.TW': '\u83ef\u901a', '2324.TW': '\u4ec1\u5bf6', '2353.TW': '\u5b8f\u7c81', '2383.TW': '\u53f0\u5149\u96fb', '2385.TW': '\u7fa4\u5149', '2404.TW': '\u6f22\u5510', '2451.TW': '\u5275\u898b', '2606.TW': '\u88d5\u6c11', '2615.TW': '\u842c\u6d77', '2727.TW': '\u738b\u54c1', '2801.TW': '\u5f70\u9280', '3036.TW': '\u6587\u6644', '3044.TW': '\u5065\u9f0e', '8299.TW': '\u7fa4\u806f', '5264.TW': '\u93a7\u52dd-KY', '6206.TW': '\u98db\u6377', '6269.TW': '\u53f0\u90e1', '6285.TW': '\u555f\u7881', '8081.TW': '\u81f4\u65b0', '3406.TW': '\u7389\u6676\u5149', '3576.TW': '\u806f\u5408\u518d\u751f', '3682.TW': '\u4e9e\u592a\u96fb', '4142.TW': '\u570b\u5149\u751f', '4906.TW': '\u6b63\u6587', '4961.TW': '\u5929\u8a60', '5522.TW': '\u9060\u96c4', '2439.TW': '\u7f8e\u5f8b', '2312.TW': '\u91d1\u5bf6', '2354.TW': '\u9d3b\u6e96', '2355.TW': '\u656c\u9d6c', '2363.TW': '\u77fd\u7d71', '2371.TW': '\u5927\u540c', '2373.TW': '\u9707\u65e6\u884c', '2401.TW': '\u51cc\u967d', '2402.TW': '\u6bc5\u5609', '2415.TW': '\u9269\u65b0', '2420.TW': '\u9577\u8208', '2421.TW': '\u5efa\u6e96', '2428.TW': '\u8208\u52e4', '2430.TW': '\u71e6\u5764', '2436.TW': '\u5049\u8a6e\u96fb', '2441.TW': '\u8d85\u8c50', '2457.TW': '\u98db\u5b8f', '0050.TW': '\u5143\u5927\u53f0\u706350'}

def analyze_stock(ticker):
    original_input = ticker
    if ticker.isdigit():
        ticker += ".TW"
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        if df.empty or len(df) < 50:
            return f"找不到 '{original_input}' 的股票資料，請確認代號是否正確。台股格式範例：2330"
        df = add_rsi(df, length=14)
        df = add_bbands(df, length=20, std=2.0)
        latest = df.iloc[-1]
        close_price = latest['Close']
        rsi = latest['RSI_14']
        bb_upper = latest['BBU_20_2.0_2.0']
        bb_lower = latest['BBL_20_2.0_2.0']
        name = STOCK_NAMES.get(ticker, "")
        display = f"{name} ({ticker})" if name else ticker
        trend = "中性觀察"
        if rsi > 75: trend = "嚴重超買，賣出警示"
        elif rsi > 70: trend = "超買區，注意回檔風險"
        elif rsi < 25: trend = "嚴重超賣，反彈機會"
        elif rsi < 30: trend = "超賣區，可關注買點"
        elif close_price > bb_upper: trend = "突破布林上軌，短線壓力漸大"
        elif close_price < bb_lower: trend = "跌破布林下軌，短線支撐區"
        # 計算新功能：預估勝率分數
        # 先轉換 df 格式符合 pv_pattern_backtest
        df_scored = df.copy().rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df_scored = add_features(df_scored)
        win_rate = calculate_win_rate_score(df_scored)

        msg = f"🔍 {display} 技術診斷報告\n"
        msg += f"--------------------\n"
        msg += f"📈 預估勝率：{win_rate}%\n"
        msg += f"💰 最新股價：{close_price:.2f}\n"
        msg += f"📊 RSI 指標：{rsi:.2f}\n"
        msg += f"⬆️ 布林上軌：{bb_upper:.2f}\n"
        msg += f"⬇️ 布林下軌：{bb_lower:.2f}\n"
        msg += f"--------------------\n"
        msg += f"💡 技術面建議：{trend}"
        return msg
    except Exception as e:
        return f"分析時發生錯誤：{str(e)}"

@app.route("/", methods=['GET'])
def health_check():
    return "OK", 200

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
    source_type = event.source.type  # 'user', 'group', or 'room'
    
    # 指令：取得 ID (可用於設定自動推播至群組)
    if user_text == "ID":
        source_id = ""
        if source_type == 'user':
            source_id = event.source.user_id
        elif source_type == 'group':
            source_id = event.source.group_id
        elif source_type == 'room':
            source_id = event.source.room_id
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"📌 您的 {source_type} ID 為：\n{source_id}")
        )
        return

    # 判斷是否為股票代號 (數字、.TW、.TWO)
    is_stock_query = user_text.isdigit() or (".TW" in user_text) or (".TWO" in user_text)
    
    if is_stock_query:
        # 由於分析可能超過 30 秒，先回傳處理中訊息
        try:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔍 正在分析中，請稍候……"))
        except:
            pass
        
        result = analyze_stock(user_text)
        
        # 使用 push_message 將結果傳回原對話框
        target_id = ""
        if source_type == 'user': target_id = event.source.user_id
        elif source_type == 'group': target_id = event.source.group_id
        elif source_type == 'room': target_id = event.source.room_id
        
        if target_id:
            line_bot_api.push_message(target_id, TextSendMessage(text=result))
    else:
        # 在群組內，若不是股票代號或 ID 指令，則不主動回話，避免干擾聊天
        if source_type == 'user':
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="👋 您好！我是您的台股即時分析師。\n\n直接傳送股票代號給我，我會馬上進行技術分析！\n\n範例：傳送「2330」查詢台積電")
            )

if __name__ == "__main__":
    # Render 會提供 PORT 環境變數，若無則預設為 10000 (Render 常用) 或 5000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
