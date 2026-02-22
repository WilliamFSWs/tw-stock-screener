#!/usr/bin/env python3
"""
批量回測 screenshots 資料夾中所有股票的價量模式。

從截圖檔名中提取股票代號，對每一檔執行 12 種價量模式回測，
最後輸出跨股票一致性分析報告。

用法：
    python backtest_all_screenshots.py
    python backtest_all_screenshots.py --screenshots-dir ./screenshots --top-patterns 5
"""

import argparse
import csv
import glob
import os
import re
import sys
import time
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from pv_pattern_backtest import (
    fetch_data, add_features, backtest_pattern, ALL_PATTERNS, get_formula_description,
)


def extract_stock_ids_from_screenshots(screenshots_dir):
    """從截圖檔名中提取股票代號。"""
    pattern = os.path.join(screenshots_dir, "*_TW_kline.png")
    files = sorted(glob.glob(pattern))

    stock_ids = []
    for f in files:
        basename = os.path.basename(f)
        # e.g. "2330_TW_kline.png" -> "2330.TW"
        match = re.match(r"(\d+)_TW_kline\.png", basename)
        if match:
            stock_ids.append(f"{match.group(1)}.TW")

    return stock_ids


def run_all_backtests(stock_ids, period="2y"):
    """對所有股票執行回測。"""
    all_results = {}
    failed = []
    total = len(stock_ids)

    for i, stock_id in enumerate(stock_ids, 1):
        print(f"\n[{i}/{total}] 回測 {stock_id}...")
        try:
            df = fetch_data(stock_id, period)
            df = add_features(df)

            results = []
            for name, func in ALL_PATTERNS.items():
                result = backtest_pattern(df, func, name)
                result["stock"] = stock_id
                results.append(result)

            all_results[stock_id] = results
            # 顯示簡要結果
            best = max(results, key=lambda x: x["win_rate_max"] if x["signals"] >= 3 else 0)
            print(f"  ✅ 最佳: {best['pattern']} (勝率 {best['win_rate_max']:.1f}%, {best['signals']} 訊號)")

        except Exception as e:
            print(f"  ❌ 失敗: {e}")
            failed.append(stock_id)

        # 避免 API rate limit
        if i % 5 == 0:
            time.sleep(1)

    return all_results, failed


def generate_report(all_results, output_dir):
    """生成跨股票分析報告。"""
    print(f"\n{'='*70}")
    print(f"📊 跨 {len(all_results)} 檔股票 回測分析報告")
    print(f"{'='*70}")

    # 1. 統計每個模式在所有股票上的表現
    pattern_stats = {}
    for pattern_name in ALL_PATTERNS.keys():
        pattern_stats[pattern_name] = {
            "win_rates_max": [],
            "win_rates_close": [],
            "avg_returns": [],
            "signal_counts": [],
            "stocks_with_signals": 0,
            "stocks_above_80": 0,
            "stocks_above_70": 0,
        }

    for stock_id, results in all_results.items():
        for r in results:
            name = r["pattern"]
            if r["signals"] >= 3:  # 至少 3 次訊號才算有效
                pattern_stats[name]["win_rates_max"].append(r["win_rate_max"])
                pattern_stats[name]["win_rates_close"].append(r["win_rate_close"])
                pattern_stats[name]["avg_returns"].append(r["avg_close_return"])
                pattern_stats[name]["signal_counts"].append(r["signals"])
                pattern_stats[name]["stocks_with_signals"] += 1
                if r["win_rate_max"] >= 80:
                    pattern_stats[name]["stocks_above_80"] += 1
                if r["win_rate_max"] >= 70:
                    pattern_stats[name]["stocks_above_70"] += 1

    # 2. 輸出排行榜
    print(f"\n{'模式':<20} {'有效股票':>8} {'≥80%股數':>8} {'平均勝率':>8} {'最低勝率':>8} {'平均報酬':>8} {'總訊號':>6}")
    print("-" * 75)

    rankings = []
    for name, stats in pattern_stats.items():
        if stats["stocks_with_signals"] >= 3:
            avg_wr = np.mean(stats["win_rates_max"])
            min_wr = min(stats["win_rates_max"]) if stats["win_rates_max"] else 0
            avg_ret = np.mean(stats["avg_returns"])
            total_signals = sum(stats["signal_counts"])
            pct_80 = stats["stocks_above_80"] / stats["stocks_with_signals"] * 100

            rankings.append({
                "name": name,
                "stocks": stats["stocks_with_signals"],
                "above_80": stats["stocks_above_80"],
                "pct_above_80": pct_80,
                "avg_wr": avg_wr,
                "min_wr": min_wr,
                "avg_ret": avg_ret,
                "total_signals": total_signals,
            })

    rankings.sort(key=lambda x: x["avg_wr"], reverse=True)

    for r in rankings:
        marker = " ⭐" if r["pct_above_80"] >= 80 else ""
        print(f"{r['name']:<20} {r['stocks']:>8} {r['above_80']:>8} "
              f"{r['avg_wr']:>7.1f}% {r['min_wr']:>7.1f}% "
              f"{r['avg_ret']:>7.2f}% {r['total_signals']:>6}{marker}")

    # 3. 找出最具普適性的模式（在 ≥80% 的股票上都有 ≥80% 勝率）
    print(f"\n{'='*70}")
    print(f"🏆 最具普適性的模式（在 ≥80% 的股票上都有 ≥80% 勝率）：")
    print(f"{'='*70}")

    universal_patterns = [r for r in rankings if r["pct_above_80"] >= 80]
    if universal_patterns:
        for r in universal_patterns:
            print(f"\n  ⭐ {r['name']}")
            print(f"     在 {r['stocks']} 檔股票中有 {r['above_80']} 檔達到 ≥80% 勝率 ({r['pct_above_80']:.0f}%)")
            print(f"     平均勝率: {r['avg_wr']:.1f}%, 最低勝率: {r['min_wr']:.1f}%")
            print(f"     平均報酬: {r['avg_ret']:.2f}%, 總訊號數: {r['total_signals']}")
            print(f"     公式: {get_formula_description(r['name'])}")
    else:
        print("\n  ⚠️ 沒有模式在 80% 以上的股票中都達到 80% 勝率")
        # 顯示最接近的
        top3 = rankings[:3]
        print(f"\n  最接近的模式：")
        for r in top3:
            print(f"  - {r['name']}: 在 {r['pct_above_80']:.0f}% 的股票上 ≥80%")

    # 4. 找出各股票的最佳買入訊號
    print(f"\n{'='*70}")
    print(f"📋 各股票當前最佳買入模式總覽（按訊號勝率排序）：")
    print(f"{'='*70}")

    stock_summary = []
    for stock_id, results in sorted(all_results.items()):
        valid = [r for r in results if r["signals"] >= 3]
        if valid:
            best = max(valid, key=lambda x: x["win_rate_max"])
            stock_summary.append({
                "stock": stock_id,
                "best_pattern": best["pattern"],
                "win_rate": best["win_rate_max"],
                "signals": best["signals"],
                "avg_return": best["avg_close_return"],
            })

    stock_summary.sort(key=lambda x: x["avg_return"], reverse=True)

    print(f"\n{'股票':>10} {'最佳模式':<20} {'勝率':>7} {'訊號':>5} {'平均報酬':>8}")
    print("-" * 55)
    for s in stock_summary[:30]:  # 顯示前 30
        print(f"{s['stock']:>10} {s['best_pattern']:<20} {s['win_rate']:>6.1f}% {s['signals']:>5} {s['avg_return']:>7.2f}%")
    if len(stock_summary) > 30:
        print(f"  ... 共 {len(stock_summary)} 檔 (僅顯示前 30)")

    # 5. 儲存完整 CSV 報表
    csv_path = os.path.join(output_dir, "backtest_report.csv")
    rows = []
    for stock_id, results in all_results.items():
        for r in results:
            rows.append({
                "股票": stock_id,
                "模式": r["pattern"],
                "訊號數": r["signals"],
                "7日最高勝率": f"{r['win_rate_max']:.1f}%",
                "7日收盤勝率": f"{r['win_rate_close']:.1f}%",
                "平均報酬": f"{r['avg_close_return']:.2f}%",
                "中位數報酬": f"{r['median_close_return']:.2f}%",
                "最大虧損": f"{r['max_drawdown']:.2f}%",
            })

    df_report = pd.DataFrame(rows)
    df_report.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n💾 完整報表已儲存: {csv_path}")

    # 6. 儲存排行榜 CSV
    ranking_csv = os.path.join(output_dir, "pattern_ranking.csv")
    df_ranking = pd.DataFrame(rankings)
    df_ranking.to_csv(ranking_csv, index=False, encoding="utf-8-sig")
    print(f"💾 模式排行已儲存: {ranking_csv}")

    return rankings, universal_patterns


def main():
    parser = argparse.ArgumentParser(description="批量回測 screenshots 資料夾中所有股票")
    parser.add_argument("--screenshots-dir", "-s", default="./screenshots",
                        help="截圖資料夾路徑 (預設: ./screenshots)")
    parser.add_argument("--period", default="2y",
                        help="歷史資料期間 (預設: 2y)")
    parser.add_argument("--output-dir", "-o", default="./screenshots",
                        help="報表輸出目錄 (預設: ./screenshots)")

    args = parser.parse_args()

    # 提取股票代號
    stock_ids = extract_stock_ids_from_screenshots(args.screenshots_dir)
    if not stock_ids:
        print(f"❌ 在 {args.screenshots_dir} 中沒有找到截圖")
        sys.exit(1)

    print(f"📂 找到 {len(stock_ids)} 檔股票截圖")
    print(f"   前 10 檔: {', '.join(stock_ids[:10])}")
    print(f"   期間: {args.period}")

    # 執行回測
    all_results, failed = run_all_backtests(stock_ids, args.period)

    if failed:
        print(f"\n⚠️ {len(failed)} 檔股票回測失敗: {', '.join(failed[:10])}")

    # 生成報告
    generate_report(all_results, args.output_dir)

    print(f"\n✅ 完成！共回測 {len(all_results)} 檔股票")


if __name__ == "__main__":
    main()
