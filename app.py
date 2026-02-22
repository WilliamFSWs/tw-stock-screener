def analyze_stock(ticker):
    original_input = ticker
    if ticker.isdigit():
        ticker += ".TW"
    
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        
        if df.empty or len(df) < 50:
            return f"❌ 找不到 '{original_input}' 的股票資料，請確認代號是否正確。\n台股格式範例：2330（系統自動補上 .TW）"
            
        df.ta.rsi(length=14, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        
        latest = df.iloc[-1]
        close_price = latest['Close']
        rsi = latest['RSI_14']
        bb_upper = latest['BBU_20_2.0_2.0']
        bb_lower = latest['BBL_20_2.0_2.0']
        
        # 直接使用字典中的中文名稱，不需要編碼轉換
        name = STOCK_NAMES.get(ticker, "")
        display = f"{name} ({ticker})" if name else ticker
        
        trend = "中性觀察"
        if rsi > 75:
            trend = "🔴 嚴重超買，賣出警示"
        elif rsi > 70:
            trend = "🟠 超買區，注意回檔風險"
        elif rsi < 25:
            trend = "🟢 嚴重超賣，反彈機會"
        elif rsi < 30:
            trend = "🟡 超賣區，可關注買點"
        elif close_price > bb_upper:
            trend = "🔴 突破布林上軌，短線壓力漸大"
        elif close_price < bb_lower:
            trend = "🟢 跌破布林下軌，短線支撐區"
        
        msg = f"🔍 {display} 技術診斷報告\n"
        msg += f"--------------------\n"
        msg += f"💰 最新股價：{close_price:.2f}\n"
        msg += f"📊 RSI 指標：{rsi:.2f}\n"
        msg += f"⬆️ 布林上軌：{bb_upper:.2f}\n"
        msg += f"⬇️ 布林下軌：{bb_lower:.2f}\n"
        msg += f"--------------------\n"
        msg += f"💡 技術面建議：{trend}"
        
        return msg
        
    except Exception as e:
        return f"⚠️ 分析時發生錯誤：{str(e)}"
