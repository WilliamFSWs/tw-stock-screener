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
    
    local_path = os.path.join("data", f"{stock_id}.csv")
    if os.path.exists(local_path):
        df = pd.read_csv(local_path, index_col=0, parse_dates=True)
        # 由於 K 線繪圖需要欄位為大寫首字母，我們將其轉回來
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        df.index.name = 'Date'
        df = df.loc[fetch_start:end_date]
        if not df.empty:
            return df

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

def generate_bulk_charts(n_samples=10, output_base_dir="./historical_charts"):
    """從 Excel 報表中隨機抽出 N 檔成功的與 N 檔失敗的訊號，自動繪製 K 線圖。"""
    try:
        df_raw = pd.read_excel("data/all_signals_raw.xlsx", engine="openpyxl")
    except Exception as e:
        print(f"❌ 無法讀取 Excel 檔案: {e}")
        return
        
    success_dir = os.path.join(output_base_dir, "success")
    failure_dir = os.path.join(output_base_dir, "failure")
    os.makedirs(success_dir, exist_ok=True)
    os.makedirs(failure_dir, exist_ok=True)
    
    wins = df_raw[df_raw["Is_Win"] == True]
    losses = df_raw[df_raw["Is_Win"] == False]
    
    if len(wins) > n_samples:
        wins = wins.sample(n_samples, random_state=42)
    if len(losses) > n_samples:
        losses = losses.sample(n_samples, random_state=42)
        
    print(f"📊 準備繪製 {len(wins)} 張成功圖表與 {len(losses)} 張失敗圖表...")
    
    def plot_row(row, out_dir, prefix):
        stock_id = row["Stock_ID"]
        signal_date = pd.to_datetime(row["Date"])
        pattern = row["Pattern"]
        
        # 抓取訊號前 30 天到訊號後 60 天
        start_date = (signal_date - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
        end_date = (signal_date + pd.Timedelta(days=90)).strftime("%Y-%m-%d")
        
        # 呼叫畫圖核心邏輯
        df = fetch_data_v2(stock_id, start_date, end_date)
        if df.empty:
            return
            
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        # 為了避免太長，我們只畫訊號附近
        # 用 signal_date 切分
        try:
            plot_start = (signal_date - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
            plot_end = (signal_date + pd.Timedelta(days=70)).strftime("%Y-%m-%d")
            df_plot = df.loc[plot_start:plot_end].copy()
            if df_plot.empty:
                return
        except Exception:
            return

        mc = mpf.make_marketcolors(up='red', down='green', edge='inherit', wick='inherit', volume='in', inherit=True)
        s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=mc, gridstyle='--', y_on_right=False)

        add_plots = [
            mpf.make_addplot(df_plot['MA5'], color='blue', width=0.8),
            mpf.make_addplot(df_plot['MA20'], color='orange', width=1.0),
            mpf.make_addplot(df_plot['MA60'], color='purple', width=1.2)
        ]
        
        import numpy as np
        
        # 標註買點 (找出日期最接近 signal_date 的 index)
        buy_idx = df_plot.index.get_indexer([signal_date], method='nearest')[0]
        marker_y = [np.nan] * len(df_plot)
        marker_y[buy_idx] = float(df_plot['Low'].iloc[buy_idx] * 0.95)
        add_plots.append(mpf.make_addplot(marker_y, type='scatter', markersize=200, marker='^', color='magenta'))

        safe_name = stock_id.replace(".", "_")
        filename = f"{prefix}_{pattern}_{safe_name}_{signal_date.strftime('%Y%m%d')}.png"
        output_path = os.path.join(out_dir, filename)
        
        title = f"[{prefix}] {stock_id} | {pattern} \nSignal: {signal_date.strftime('%Y-%m-%d')} | EV/Win: {prefix}"
        
        mpf.plot(
            df_plot, type='candle', style=s, title=title,
            ylabel='Price', ylabel_lower='Volume', volume=True,
            addplot=add_plots, figsize=(16, 10), savefig=output_path, tight_layout=True
        )
        print(f"✅ {prefix} 圖表已儲存: {output_path}")

    # 開始畫圖
    for _, row in wins.iterrows():
        plot_row(row, success_dir, "WIN")
        
    for _, row in losses.iterrows():
        plot_row(row, failure_dir, "LOSS")
        
    print(f"\n🎉 批量畫圖完成！圖表已存入 {output_base_dir}/success 與 {output_base_dir}/failure")


def main():
    parser = argparse.ArgumentParser(description="在地化歷史 K 線生成器")
    parser.add_argument("--stock", "-s", help="股票代號 (例: 2330.TW)")
    parser.add_argument("--start", default="2021-01-01", help="開始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", default="2021-12-31", help="結束日期 (YYYY-MM-DD)")
    parser.add_argument("--output-dir", "-o", default="./historical_charts", help="輸出目錄")
    parser.add_argument("--bulk", type=int, help="隨機抽出 N 筆成功與失敗的訊號並畫圖 (讀取 data/all_signals_raw.xlsx)")
    
    args = parser.parse_args()
    
    if args.bulk:
        generate_bulk_charts(args.bulk, args.output_dir)
    elif args.stock:
        generate_chart(args.stock, args.start, args.end, args.output_dir)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
