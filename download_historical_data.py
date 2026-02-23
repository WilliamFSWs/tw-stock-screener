#!/usr/bin/env python3
import os
import yfinance as yf
import pandas as pd
from datetime import datetime

# 只需要下載前 150 大或 250 大市值股票，我們可以使用已有的 daily_scanner 的 get_top_stocks 函式
from daily_scanner import get_top_stocks

def download_historical_data(start_date="2019-01-01", end_date="2026-12-31", top_n=250):
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"📡 準備取得前 {top_n} 大股票...")
    stocks = get_top_stocks(top_n)
    stock_ids = [f"{s['code']}.TW" for s in stocks]
    
    # yfinance auto_adjust 時需要多抓 120 天前來算 MA，我們在儲存時可以連這段資料一起留著，方便未來回測
    fetch_start = (datetime.strptime(start_date, "%Y-%m-%d") - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    
    total = len(stock_ids)
    failed = []
    
    for i, stock_id in enumerate(stock_ids, 1):
        file_path = os.path.join(output_dir, f"{stock_id}.csv")
        if os.path.exists(file_path):
            print(f"[{i}/{total}] {stock_id} 已經存在，跳過下載。")
            continue
            
        print(f"[{i}/{total}] 正在下載 {stock_id} 資料 ({fetch_start} ~ {end_date})...")
        try:
            df = yf.download(stock_id, start=fetch_start, end=end_date, auto_adjust=True, progress=False)
            if df.empty:
                print(f"  ❌ {stock_id} 資料空白")
                failed.append(stock_id)
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
            
            df.to_csv(file_path)
            print(f"  ✅ {stock_id} 寫入 {file_path}")
        except Exception as e:
            print(f"  ❌ 發生錯誤 {stock_id}: {e}")
            failed.append(stock_id)
            
    print(f"\n下載完成！共有 {len(failed)} 檔股票失敗。")
    if failed:
        print(f"失敗清單: {failed}")

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=50, help="Number of top stocks to download")
    args = parser.parse_args()
    download_historical_data(top_n=args.top)
