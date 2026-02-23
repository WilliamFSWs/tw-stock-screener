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
    """取得特定日期範圍的歷史資料。優先從本地 data/ 資料夾讀取。"""
    # 稍微多抓一點前面資料，以便計算均線 (MA20, MA60)
    adjusted_start = (datetime.strptime(start_date, "%Y-%m-%d") - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    
    # 嘗試讀取本地資料
    local_path = os.path.join("data", f"{stock_id}.csv")
    if os.path.exists(local_path):
        df = pd.read_csv(local_path, index_col=0, parse_dates=True)
        # 過濾日期區間
        df = df.loc[adjusted_start:end_date]
        if not df.empty:
            return df
            
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
        pattern_stats[name] = {"win_rates": [], "signals": 0, "stocks_with_signals": 0, "avg_returns": [], "max_drawdowns": [], "yearly": {}}

    for stock_id, results in all_results.items():
        for r in results:
            if r["signals"] >= 1:
                pattern_stats[r["pattern"]]["win_rates"].append(r["win_rate_max"])
                pattern_stats[r["pattern"]]["signals"] += r["signals"]
                pattern_stats[r["pattern"]]["stocks_with_signals"] += 1
                pattern_stats[r["pattern"]]["avg_returns"].append(r["avg_close_return"])
                pattern_stats[r["pattern"]]["max_drawdowns"].append(r["max_drawdown"])
                
                for year, y_stats in r.get("yearly_stats", {}).items():
                    if year not in pattern_stats[r["pattern"]]["yearly"]:
                        pattern_stats[r["pattern"]]["yearly"][year] = {"win_rates": [], "signals": 0, "avg_returns": []}
                    pattern_stats[r["pattern"]]["yearly"][year]["win_rates"].append(y_stats["win_rate"])
                    pattern_stats[r["pattern"]]["yearly"][year]["signals"] += y_stats["signals"]
                    pattern_stats[r["pattern"]]["yearly"][year]["avg_returns"].append(y_stats["avg_return"])

    print(f"\n{'模式':<20} {'有效股票':>8} {'平均勝率':>10} {'平均報酬率':>10} {'平均最大跌幅':>10} {'總訊號':>6}")
    print("-" * 75)
    
    rankings = []
    for name, stats in pattern_stats.items():
        if stats["stocks_with_signals"] > 0:
            avg_wr = np.mean(stats["win_rates"])
            avg_ret = np.mean(stats["avg_returns"])
            avg_dd = np.mean(stats["max_drawdowns"])
            rankings.append({
                "name": name,
                "stocks": stats["stocks_with_signals"],
                "avg_wr": avg_wr,
                "avg_ret": avg_ret,
                "avg_dd": avg_dd,
                "signals": stats["signals"]
            })

    rankings.sort(key=lambda x: x["avg_wr"], reverse=True)
    for r in rankings:
        print(f"{r['name']:<20} {r['stocks']:>8} {r['avg_wr']:>9.1f}% {r['avg_ret']:>9.1f}% {r['avg_dd']:>9.1f}% {r['signals']:>6}")

    print(f"\n{'='*75}")
    print(f"📅 各年度勝率與報酬率拆解")
    print(f"{'='*75}")
    
    all_years = set()
    for name, stats in pattern_stats.items():
        all_years.update(stats["yearly"].keys())
    
    sorted_years = sorted(list(all_years))
    
    for r in rankings:
        name = r['name']
        print(f"\n➤ {name}:")
        print(f"  {'年度':<6} | {'勝率':>8} | {'平均報酬':>8} | {'訊號數':>6}")
        print(f"  {'-'*40}")
        yearly_data = pattern_stats[name]["yearly"]
        for year in sorted_years:
            if year in yearly_data and yearly_data[year]["signals"] > 0:
                y_wr = np.mean(yearly_data[year]["win_rates"])
                y_ret = np.mean(yearly_data[year]["avg_returns"])
                y_sig = yearly_data[year]["signals"]
                print(f"  {year:<6} | {y_wr:>7.1f}% | {y_ret:>7.1f}% | {y_sig:>6}")

    # 生成個股期望值 CSV 及合併所有的交易細節 (Raw Data)
    csv_data = []
    all_raw_signals = []
    
    # 設定使用者停損點參數來計算期望值
    stop_loss = 0.07 
    
    for stock_id, results in all_results.items():
        for r in results:
            if r["signals"] > 0:
                win_rate_dec = r["win_rate_max"] / 100.0
                loss_rate_dec = 1.0 - win_rate_dec
                avg_win_ret = r["avg_close_return"] / 100.0 if r["avg_close_return"] > 0 else 0.085 # fallback conservative win if average is suppressed by losses
                
                # 計算期望值: (勝率 * 平均獲利) - (敗率 * 停損趴數)
                ev = (win_rate_dec * avg_win_ret) - (loss_rate_dec * stop_loss)
                
                csv_data.append({
                    "Stock_ID": stock_id,
                    "Pattern": r["pattern"],
                    "Signals": r["signals"],
                    "Win_Rate(%)": round(r["win_rate_max"], 2),
                    "Avg_Return(%)": round(r["avg_close_return"], 2),
                    "Max_Drawdown(%)": round(r["max_drawdown"], 2),
                    "Expected_Value(%)": round(ev * 100, 2)
                })
                
                # 收集每一筆交易詳細資訊
                for detail in r.get("signal_details", []):
                    detail_record = {
                        "Stock_ID": stock_id,
                        "Pattern": r["pattern"]
                    }
                    detail_record.update(detail)
                    all_raw_signals.append(detail_record)
                
    if csv_data:
        df_csv = pd.DataFrame(csv_data)
        # 依照期望值由高到低排序
        df_csv = df_csv.sort_values(by=["Expected_Value(%)", "Win_Rate(%)"], ascending=[False, False])
        csv_path = os.path.join("data", "stock_ev_report.csv")
        try:
            df_csv.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"\n✅ 個股期望值報表已匯出至: {csv_path}")
        except PermissionError:
            import time
            fallback_ts = int(time.time())
            fallback_path = os.path.join("data", f"stock_ev_report_{fallback_ts}.csv")
            df_csv.to_csv(fallback_path, index=False, encoding="utf-8-sig")
            print(f"\n✅ 個股期望值報表 (檔案被鎖定，改存備份) 已匯出至: {fallback_path}")

    if all_raw_signals:
        df_raw = pd.DataFrame(all_raw_signals)
        # 以日期排序方便人類觀察
        df_raw = df_raw.sort_values(by=["Date", "Stock_ID"])
        excel_path = os.path.join("data", "all_signals_raw.xlsx")
        try:
            df_raw.to_excel(excel_path, index=False, engine="openpyxl")
            print(f"✅ 詳細訊號報表 (Raw Data) 已匯出至: {excel_path}")
        except PermissionError:
            import time
            fallback_ts = int(time.time())
            fallback_path = os.path.join("data", f"all_signals_raw_{fallback_ts}.xlsx")
            df_raw.to_excel(fallback_path, index=False, engine="openpyxl")
            print(f"✅ 詳細訊號報表 (檔案被鎖定，改存備份) 已匯出至: {fallback_path}")
        except Exception as e:
            print(f"❌ 無法匯出 Excel (可能未安裝 openpyxl): {e}")

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
