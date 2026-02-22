#!/usr/bin/env python3
"""
歷史特定期間回測工具
用於驗證模式在特定年份（如 2021 牛市轉 2022 熊市）的表現。
"""

import argparse
import os
import sys
import json
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

from pv_pattern_backtest import (
    add_features, backtest_pattern, ALL_PATTERNS, get_formula_description
)
from daily_scanner import get_top_stocks

def fetch_data_historical(stock_id, start_date, end_date):
    """取得特定日期範圍的歷史資料。"""
    # 稍微多抓一點前面資料，以便計算均線 (MA20, MA60)
    adjusted_start = (datetime.strptime(start_date, "%Y-%m-%d") - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    
    print(f"📡 下載 {stock_id} 歷史資料 ({start_date} ~ {end_date})...")
    df = yf.download(stock_id, start=adjusted_start, end=end_date, auto_adjust=True, progress=False)
    
    if df.empty:
        return df

    # Flatten multi-level columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    return df

def run_historical_backtest(stock_ids, start_date, end_date):
    """對一組股票執行特定期間的回測。"""
    all_results = {}
    failed = []
    total = len(stock_ids)

    for i, stock_id in enumerate(stock_ids, 1):
        print(f"\r📊 進度 [{i}/{total}] {stock_id}...", end="")
        try:
            df = fetch_data_historical(stock_id, start_date, end_date)
            if df.empty:
                failed.append(stock_id)
                continue
                
            df = add_features(df)
            
            # 過濾回特定的開始日期
            df = df[df.index >= start_date]
            
            if df.empty:
                failed.append(stock_id)
                continue

            results = []
            for name, func in ALL_PATTERNS.items():
                res = backtest_pattern(df, func, name)
                res["stock"] = stock_id
                results.append(res)

            all_results[stock_id] = results
        except Exception as e:
            failed.append(stock_id)

    print("\n✅ 回測完成！正在生成分析報告...")
    return all_results, failed

def generate_historical_report(all_results, start_date, end_date):
    """生成摘要報告。"""
    print(f"\n{'='*75}")
    print(f"📈 歷史回測報告 ({start_date} ~ {end_date})")
    print(f"📊 參與股票數: {len(all_results)} 檔")
    print(f"{'='*75}")

    pattern_stats = {}
    for name in ALL_PATTERNS.keys():
        pattern_stats[name] = {"win_rates": [], "signals": 0, "stocks_with_signals": 0}

    for stock_id, results in all_results.items():
        for r in results:
            if r["signals"] >= 1:
                pattern_stats[r["pattern"]]["win_rates"].append(r["win_rate_max"])
                pattern_stats[r["pattern"]]["signals"] += r["signals"]
                pattern_stats[r["pattern"]]["stocks_with_signals"] += 1

    print(f"\n{'模式':<20} {'有效股票':>8} {'平均勝率':>10} {'總訊號':>6}")
    print("-" * 50)
    
    rankings = []
    for name, stats in pattern_stats.items():
        if stats["stocks_with_signals"] > 0:
            avg_wr = np.mean(stats["win_rates"])
            rankings.append({
                "name": name,
                "stocks": stats["stocks_with_signals"],
                "avg_wr": avg_wr,
                "signals": stats["signals"]
            })

    rankings.sort(key=lambda x: x["avg_wr"], reverse=True)
    for r in rankings:
        print(f"{r['name']:<20} {r['stocks']:>8} {r['avg_wr']:>9.1f}% {r['signals']:>6}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2022-12-31")
    parser.add_argument("--top", type=int, default=50)
    args = parser.parse_args()

    # 1. 取得股票名單
    stocks = get_top_stocks(args.top)
    stock_ids = [f"{s['code']}.TW" for s in stocks]

    # 2. 執行回測
    results, failed = run_historical_backtest(stock_ids, args.start, args.end)

    # 3. 生成報告
    generate_historical_report(results, args.start, args.end)

if __name__ == "__main__":
    main()
