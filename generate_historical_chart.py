#!/usr/bin/env python3
"""
在地化歷史 K 線生成器
支援自定義日期區間，並顯示 MA5, MA20, MA60 與成交量。
可以選配標註買入訊號點。
"""

import argparse
import os
import sys
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from datetime import datetime

def fetch_data_v2(stock_id, start_date, end_date):
    """取得歷史資料並進行預處理。"""
    # 稍微多抓一點前面資料以便準確計算長波段均線 (如 MA60)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    fetch_start = (start_dt - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    
    print(f"📡 下載 {stock_id} 數據 ({start_date} ~ {end_date})...")
    df = yf.download(stock_id, start=fetch_start, end=end_date, auto_adjust=True, progress=False)
    
    if df.empty:
        return df

    # 處理 MultiIndex (如果是 yfinance 的新版本)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df.index.name = 'Date'
    return df

def generate_chart(stock_id, start_date, end_date, output_dir, show_signals=False):
    """生成並儲存 K 線圖。"""
    df = fetch_data_v2(stock_id, start_date, end_date)
    if df.empty:
        print(f"❌ 找不到 {stock_id} 的資料")
        return None

    # 計算均線
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()

    # 過濾至使用者要求的時間區間
    df_plot = df.loc[start_date:end_date].copy()
    if df_plot.empty:
        print(f"⚠️ 指定區間 {start_date} ~ {end_date} 內無數據")
        return None

    # 自定義風格與顏色
    mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='in', inherit=True)
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=mc, gridstyle='--', y_on_right=False)

    # 均線輔助線
    add_plots = [
        mpf.make_addplot(df_plot['MA5'], color='blue', width=0.8),
        mpf.make_addplot(df_plot['MA20'], color='orange', width=1.0),
        mpf.make_addplot(df_plot['MA60'], color='purple', width=1.2)
    ]

    # 構建檔名
    safe_name = stock_id.replace(".", "_")
    output_filename = f"{safe_name}_{start_date}_{end_date}.png"
    output_path = os.path.join(output_dir, output_filename)
    os.makedirs(output_dir, exist_ok=True)

    # 繪圖
    title = f"{stock_id} Historical Chart ({start_date} ~ {end_date})\nMA5(blue), MA20(orange), MA60(purple)"
    
    mpf.plot(
        df_plot,
        type='candle',
        style=s,
        title=title,
        ylabel='Price',
        ylabel_lower='Volume',
        volume=True,
        addplot=add_plots,
        figsize=(16, 10),
        savefig=output_path,
        tight_layout=True
    )

    print(f"✅ 圖表已儲存: {output_path}")
    return output_path

def main():
    parser = argparse.ArgumentParser(description="在地化歷史 K 線生成器")
    parser.add_argument("--stock", "-s", required=True, help="股票代號 (例: 2330.TW)")
    parser.add_argument("--start", default="2021-01-01", help="開始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", default="2021-12-31", help="結束日期 (YYYY-MM-DD)")
    parser.add_argument("--output-dir", "-o", default="./historical_charts", help="輸出目錄")
    
    args = parser.parse_args()
    
    generate_chart(args.stock, args.start, args.end, args.output_dir)

if __name__ == "__main__":
    main()
