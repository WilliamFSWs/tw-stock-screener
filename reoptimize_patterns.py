#!/usr/bin/env python3
"""
價量模式月度優化工具 (Re-optimizer)

功能：
1. 下載台股前 100 大市值近期數據 (近 6 個月)
2. 針對 12 種價量模式進行「近期回測」
3. 自動評估哪些模式在當前市場（牛市或熊市）中勝率較高
4. 產生 `best_patterns_config.json` 供 `daily_scanner.py` 優先使用

用途：
- 每個月執行一次，確保買入訊號與當前市場步調一致。
"""

import os
import json
import argparse
import pandas as pd
from datetime import datetime, timedelta
import pytz

# 引入現有的功能
from pv_pattern_backtest import fetch_data, add_features, ALL_PATTERNS, backtest_pattern
from daily_scanner import get_top_stocks

def run_optimization(top_n=50, lookback_months=6):
    """執行近期回測，找出當前最強模式。"""
    print(f"🚀 開始週期性優化 (前 {top_n} 檔, 回測近 {lookback_months} 個月)...")
    
    # 1. 取得最新股票清單
    stocks = get_top_stocks(top_n)
    
    # 2. 彙總回測結果
    pattern_stats = {name: [] for name in ALL_PATTERNS.keys()}
    
    total = len(stocks)
    for i, stock in enumerate(stocks, 1):
        stock_id = f"{stock['code']}.TW"
        print(f"\r📊 分析中 [{i}/{total}] {stock_id}...", end="")
        
        try:
            # 取得近期資料
            df = fetch_data(stock_id, period=f"{lookback_months}mo")
            if len(df) < 20: continue
            df = add_features(df)
            
            # 測試每種模式
            for name, func in ALL_PATTERNS.items():
                res = backtest_pattern(df, func, name)
                if res["signals"] > 0:
                    pattern_stats[name].append(res)
        except Exception as e:
            continue

    print("\n✅ 回測完成，正在計算當前最佳模式...")

    # 3. 分析整體表現
    results = []
    for name, stats in pattern_stats.items():
        if not stats: continue
        
        df_stats = pd.DataFrame(stats)
        avg_win_rate = df_stats["win_rate_max"].mean()
        avg_return = df_stats["avg_return_max"].mean()
        total_signals = df_stats["signals"].sum()
        consistency = (df_stats["win_rate_max"] >= 80).mean() # 有多少比例的股票達到 80% 勝率

        results.append({
            "pattern": name,
            "avg_win_rate": round(avg_win_rate, 2),
            "avg_return": round(avg_return, 2),
            "consistency": round(consistency, 2),
            "signals": int(total_signals)
        })

    # 按勝率與普適性排序
    df_results = pd.DataFrame(results).sort_values(by=["consistency", "avg_win_rate"], ascending=False)

    # 4. 輸出配置檔案
    config = {
        "last_updated": datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d %H:%M"),
        "best_patterns": df_results[df_results["consistency"] >= 0.7]["pattern"].tolist(),
        "ranking": results
    }

    with open("best_patterns_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n🏆 當前市場最強模式排行榜：")
    print(df_results.head(10).to_string(index=False))
    print(f"\n💾 已儲存配置: best_patterns_config.json")
    
    if config["best_patterns"]:
        print(f"📡 建議優先關注模式: {', '.join(config['best_patterns'][:3])}")
    else:
        print("⚠️ 警告：當前市場環境極差，沒有任何模式能達到 70% 普適性。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--months", type=int, default=6)
    args = parser.parse_args()
    
    run_optimization(top_n=args.top, lookback_months=args.months)
