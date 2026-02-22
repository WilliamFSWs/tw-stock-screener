#!/usr/bin/env python3
"""
價量關係分析 — 7日上漲高勝率模型回測

分析多種價量模式，找出買進後 7 日內上漲機率 ≥ 80% 的訊號組合。
在一檔股票上發現模式，再用另一檔股票驗證。

用法：
    python pv_pattern_backtest.py
    python pv_pattern_backtest.py --train 2330.TW --validate 2308.TW 2454.TW
"""

import argparse
import os
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")


# ============================================================
# 資料準備
# ============================================================

def fetch_data(stock_id, period="2y"):
    """取得歷史日K資料。"""
    print(f"📡 下載 {stock_id} 歷史資料 ({period})...")
    df = yf.download(stock_id, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"無法取得 {stock_id} 的資料")

    # Flatten multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    print(f"  ✅ 取得 {len(df)} 筆日K資料 ({df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')})")
    return df


def add_features(df):
    """計算技術指標和衍生特徵。"""
    d = df.copy()

    # 均線
    d["ma5"] = d["close"].rolling(5).mean()
    d["ma10"] = d["close"].rolling(10).mean()
    d["ma20"] = d["close"].rolling(20).mean()
    d["ma60"] = d["close"].rolling(60).mean()

    # 量均線
    d["vol_ma5"] = d["volume"].rolling(5).mean()
    d["vol_ma20"] = d["volume"].rolling(20).mean()

    # K線特徵
    d["body"] = d["close"] - d["open"]  # 正=紅K, 負=綠K
    d["body_abs"] = d["body"].abs()
    d["upper_shadow"] = d["high"] - d[["open", "close"]].max(axis=1)
    d["lower_shadow"] = d[["open", "close"]].min(axis=1) - d["low"]
    d["range"] = d["high"] - d["low"]
    d["is_red"] = (d["close"] > d["open"]).astype(int)

    # 漲跌幅
    d["pct_change"] = d["close"].pct_change()

    # 量比 (今日量 / MA5量)
    d["vol_ratio_ma5"] = d["volume"] / d["vol_ma5"]
    # 量比 (今日量 / MA20量)
    d["vol_ratio_ma20"] = d["volume"] / d["vol_ma20"]

    # 股價相對MA20的偏離度
    d["ma20_deviation"] = (d["close"] - d["ma20"]) / d["ma20"]

    # 連漲/連跌天數
    d["consecutive_down"] = 0
    d["consecutive_up"] = 0
    count_down = 0
    count_up = 0
    for i in range(len(d)):
        if d["pct_change"].iloc[i] < 0:
            count_down += 1
            count_up = 0
        elif d["pct_change"].iloc[i] > 0:
            count_up += 1
            count_down = 0
        else:
            count_down = 0
            count_up = 0
        d.iloc[i, d.columns.get_loc("consecutive_down")] = count_down
        d.iloc[i, d.columns.get_loc("consecutive_up")] = count_up

    # 近 N 日最高/最低
    d["high_5d"] = d["high"].rolling(5).max()
    d["low_5d"] = d["low"].rolling(5).min()
    d["high_20d"] = d["high"].rolling(20).max()
    d["low_20d"] = d["low"].rolling(20).min()

    # RSI (14日)
    delta = d["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    d["rsi14"] = 100 - (100 / (1 + rs))

    # 前一日量
    d["prev_volume"] = d["volume"].shift(1)

    # 7日後最高價 & 收盤價（用於計算勝率）
    d["future_max_7d"] = d["high"].shift(-1).rolling(7).max().shift(-6)
    d["future_close_7d"] = d["close"].shift(-7)
    d["future_return_7d"] = (d["future_close_7d"] - d["close"]) / d["close"]
    d["future_max_return_7d"] = (d["future_max_7d"] - d["close"]) / d["close"]

    return d.dropna(subset=["ma20", "vol_ma20", "rsi14"])


# ============================================================
# 價量模式定義
# ============================================================

def pattern_volume_shrink_stable(d):
    """模式1: 量縮價穩 — 成交量<MA20的50%, 但跌幅<1%"""
    return (d["vol_ratio_ma20"] < 0.5) & (d["pct_change"].abs() < 0.01)


def pattern_volume_surge_red(d):
    """模式2: 量增紅K — 成交量>MA5的2倍, 且收紅K"""
    return (d["vol_ratio_ma5"] > 2.0) & (d["is_red"] == 1)


def pattern_ma20_support_volume(d):
    """模式3: 均線支撐+放量 — 收盤在MA20±2%, 量>MA5"""
    return (d["ma20_deviation"].abs() < 0.02) & (d["vol_ratio_ma5"] > 1.0) & (d["is_red"] == 1)


def pattern_long_lower_shadow(d):
    """模式4: 長下影線+放量 — 下影線>實體2倍, 量>MA20"""
    has_lower_shadow = d["lower_shadow"] > (d["body_abs"] * 2)
    has_volume = d["vol_ratio_ma20"] > 1.0
    return has_lower_shadow & has_volume


def pattern_consecutive_down_red(d):
    """模式5: 連跌反轉 — 連跌3日以上後出現紅K"""
    prev_down = d["consecutive_down"].shift(1) >= 3
    return prev_down & (d["is_red"] == 1)


def pattern_volume_divergence(d):
    """模式6: 價量背離 — 價格觸及20日低點, 但量低於MA20"""
    near_low = (d["close"] - d["low_20d"]) / d["low_20d"] < 0.02
    low_volume = d["vol_ratio_ma20"] < 0.8
    return near_low & low_volume


def pattern_rsi_oversold_volume_shrink(d):
    """模式7: RSI超賣+量縮 — RSI<30, 量<MA20"""
    return (d["rsi14"] < 30) & (d["vol_ratio_ma20"] < 1.0)


def pattern_ma_golden_cross_volume(d):
    """模式8: 短均線黃金交叉+量增 — MA5上穿MA20, 量>MA5"""
    ma5_cross_ma20 = (d["ma5"] > d["ma20"]) & (d["ma5"].shift(1) <= d["ma20"].shift(1))
    volume_up = d["vol_ratio_ma5"] > 1.2
    return ma5_cross_ma20 & volume_up


def pattern_volume_shrink_then_surge(d):
    """模式9: 連續量縮後爆量紅K — 前3日量縮<MA20的60%, 今日量>MA5且紅K"""
    vol_shrink_1 = d["vol_ratio_ma20"].shift(1) < 0.6
    vol_shrink_2 = d["vol_ratio_ma20"].shift(2) < 0.6
    vol_shrink_3 = d["vol_ratio_ma20"].shift(3) < 0.6
    today_surge = (d["vol_ratio_ma5"] > 1.5) & (d["is_red"] == 1)
    return vol_shrink_1 & vol_shrink_2 & vol_shrink_3 & today_surge


def pattern_combo_best(d):
    """模式10: 最佳組合 — 價在MA20附近, RSI<50, 量比MA20低, 出紅K"""
    near_ma20 = d["ma20_deviation"].abs() < 0.03
    rsi_low = d["rsi14"] < 50
    vol_low = d["vol_ratio_ma20"] < 0.8
    red_k = d["is_red"] == 1
    return near_ma20 & rsi_low & vol_low & red_k


def pattern_above_ma_all(d):
    """模式11: 多頭排列紅K — 收盤>MA5>MA10>MA20, 紅K, 量>MA5"""
    bullish_align = (d["close"] > d["ma5"]) & (d["ma5"] > d["ma10"]) & (d["ma10"] > d["ma20"])
    return bullish_align & (d["is_red"] == 1) & (d["vol_ratio_ma5"] > 1.0)


def pattern_pullback_in_uptrend(d):
    """模式12: 多頭回檔 — MA20上升, 價格回測MA10附近, 量縮, 收紅K"""
    ma20_rising = d["ma20"] > d["ma20"].shift(5)
    near_ma10 = ((d["close"] - d["ma10"]) / d["ma10"]).abs() < 0.02
    vol_shrink = d["vol_ratio_ma20"] < 0.8
    return ma20_rising & near_ma10 & vol_shrink & (d["is_red"] == 1)


# 所有模式的定義
ALL_PATTERNS = {
    "P01_量縮價穩": pattern_volume_shrink_stable,
    "P02_量增紅K": pattern_volume_surge_red,
    "P03_均線支撐放量": pattern_ma20_support_volume,
    "P04_長下影線放量": pattern_long_lower_shadow,
    "P05_連跌反轉紅K": pattern_consecutive_down_red,
    "P06_價量背離": pattern_volume_divergence,
    "P07_RSI超賣量縮": pattern_rsi_oversold_volume_shrink,
    "P08_黃金交叉量增": pattern_ma_golden_cross_volume,
    "P09_量縮後爆量紅K": pattern_volume_shrink_then_surge,
    "P10_組合訊號": pattern_combo_best,
    "P11_多頭排列紅K": pattern_above_ma_all,
    "P12_多頭回檔": pattern_pullback_in_uptrend,
}


# ============================================================
# 回測引擎
# ============================================================

def backtest_pattern(df, pattern_func, pattern_name):
    """
    回測單一模式。

    Returns:
        dict: 包含勝率、訊號次數、平均報酬等統計
    """
    d = df.copy()
    signals = pattern_func(d)

    # 確保有 future 資料可算
    valid = signals & d["future_max_7d"].notna() & d["future_close_7d"].notna()
    signal_dates = d[valid].index

    if len(signal_dates) == 0:
        return {
            "pattern": pattern_name,
            "signals": 0,
            "win_rate_max": 0,
            "win_rate_close": 0,
            "avg_max_return": 0,
            "avg_close_return": 0,
            "median_close_return": 0,
            "max_drawdown": 0,
        }

    signal_data = d.loc[signal_dates]

    # 勝率（7日內最高價 > 買入收盤價）
    wins_max = (signal_data["future_max_return_7d"] > 0).sum()
    # 勝率（7日後收盤價 > 買入收盤價）
    wins_close = (signal_data["future_return_7d"] > 0).sum()

    return {
        "pattern": pattern_name,
        "signals": len(signal_dates),
        "win_rate_max": wins_max / len(signal_dates) * 100,
        "win_rate_close": wins_close / len(signal_dates) * 100,
        "avg_max_return": signal_data["future_max_return_7d"].mean() * 100,
        "avg_close_return": signal_data["future_return_7d"].mean() * 100,
        "median_close_return": signal_data["future_return_7d"].median() * 100,
        "max_drawdown": signal_data["future_return_7d"].min() * 100,
    }


def run_backtest(stock_id, label="", period="2y"):
    """對一檔股票執行所有模式的回測。"""
    df = fetch_data(stock_id, period)
    df = add_features(df)

    print(f"\n{'='*70}")
    print(f"📊 {label} 回測結果 — {stock_id}")
    print(f"{'='*70}")
    print(f"{'模式':<20} {'訊號數':>6} {'7日最高勝率':>10} {'7日收盤勝率':>10} {'平均報酬%':>8} {'中位數%':>7}")
    print("-" * 70)

    results = []
    for name, func in ALL_PATTERNS.items():
        result = backtest_pattern(df, func, name)
        results.append(result)

        wr_max = f"{result['win_rate_max']:.1f}%"
        wr_close = f"{result['win_rate_close']:.1f}%"
        avg_ret = f"{result['avg_close_return']:.2f}%"
        med_ret = f"{result['median_close_return']:.2f}%"
        marker = " ⭐" if result["win_rate_max"] >= 80 and result["signals"] >= 5 else ""

        print(f"{result['pattern']:<20} {result['signals']:>6} {wr_max:>10} {wr_close:>10} {avg_ret:>8} {med_ret:>7}{marker}")

    # 找出 ≥80% 勝率的模式
    winners = [r for r in results if r["win_rate_max"] >= 80 and r["signals"] >= 5]
    if winners:
        print(f"\n🏆 勝率 ≥ 80% 且訊號數 ≥ 5 的模式：")
        for w in sorted(winners, key=lambda x: x["win_rate_max"], reverse=True):
            print(f"  ⭐ {w['pattern']}: 勝率 {w['win_rate_max']:.1f}%, "
                  f"訊號 {w['signals']} 次, 平均報酬 {w['avg_close_return']:.2f}%")
    else:
        # 顯示最高勝率的
        best = max(results, key=lambda x: x["win_rate_max"] if x["signals"] >= 3 else 0)
        print(f"\n💡 最高勝率模式: {best['pattern']} ({best['win_rate_max']:.1f}%, {best['signals']} 次)")

    return results, df


def derive_formula(all_results):
    """從回測結果推導最佳公式。"""
    print(f"\n{'='*70}")
    print(f"📐 推導最佳買入公式")
    print(f"{'='*70}")

    # 匯總所有股票的結果
    pattern_scores = {}
    for stock_id, results in all_results.items():
        for r in results:
            name = r["pattern"]
            if name not in pattern_scores:
                pattern_scores[name] = []
            if r["signals"] >= 3:
                pattern_scores[name].append({
                    "stock": stock_id,
                    "win_rate": r["win_rate_max"],
                    "signals": r["signals"],
                    "avg_return": r["avg_close_return"],
                })

    # 找出跨股票一致性高的模式
    print("\n📋 跨股票一致性分析：")
    print(f"{'模式':<20} {'股票數':>6} {'平均勝率':>8} {'最低勝率':>8} {'總訊號':>6}")
    print("-" * 55)

    consistent_patterns = []
    for name, scores in pattern_scores.items():
        if len(scores) >= 2:
            avg_wr = np.mean([s["win_rate"] for s in scores])
            min_wr = min(s["win_rate"] for s in scores)
            total_signals = sum(s["signals"] for s in scores)
            marker = " ✅" if min_wr >= 70 else ""
            print(f"{name:<20} {len(scores):>6} {avg_wr:>7.1f}% {min_wr:>7.1f}% {total_signals:>6}{marker}")

            if min_wr >= 70:
                consistent_patterns.append((name, avg_wr, min_wr, total_signals))

    # 輸出公式
    print(f"\n{'='*70}")
    print("📐 最佳買入公式推導結果：")
    print(f"{'='*70}")

    if consistent_patterns:
        consistent_patterns.sort(key=lambda x: x[1], reverse=True)
        print("\n跨股票驗證後，以下模式維持高勝率：\n")
        for name, avg_wr, min_wr, total in consistent_patterns:
            print(f"  ✅ {name}")
            print(f"     平均勝率: {avg_wr:.1f}%, 最低勝率: {min_wr:.1f}%, 總訊號數: {total}")
            # 輸出公式定義
            print(f"     公式: {get_formula_description(name)}")
            print()
    else:
        print("\n⚠️  沒有任何模式在所有股票上都達到 80% 以上勝率。")
        print("    這說明價量關係的預測力因股票特性而異。")
        print("    建議：使用多模式組合 + 大盤環境篩選來提高勝率。")

    # 額外提出組合建議
    print("\n💡 建議的組合公式（任一條件成立即可買入）：")
    if consistent_patterns:
        conditions = [f"    - {name}" for name, _, _, _ in consistent_patterns[:3]]
        print("  當以下任一條件成立時買入：")
        for c in conditions:
            print(c)
    else:
        print("  結合以下條件（至少滿足2個）：")
        print("    1. RSI(14) < 40")
        print("    2. 成交量 < 20日均量的 70%")
        print("    3. 股價在 MA20 ±3% 範圍內")
        print("    4. 當日為紅K（收盤 > 開盤）")
        print("    5. MA20 呈上升趨勢")

    return consistent_patterns


def get_formula_description(pattern_name):
    """返回模式的數學公式描述。"""
    formulas = {
        "P01_量縮價穩": "Volume < MA20_vol × 0.5  AND  |ΔP/P| < 1%",
        "P02_量增紅K": "Volume > MA5_vol × 2.0  AND  Close > Open",
        "P03_均線支撐放量": "|Close - MA20| / MA20 < 2%  AND  Volume > MA5_vol  AND  Close > Open",
        "P04_長下影線放量": "LowerShadow > |Body| × 2  AND  Volume > MA20_vol",
        "P05_連跌反轉紅K": "ConsecutiveDown(t-1) ≥ 3  AND  Close > Open",
        "P06_價量背離": "(Close - Low20D) / Low20D < 2%  AND  Volume < MA20_vol × 0.8",
        "P07_RSI超賣量縮": "RSI(14) < 30  AND  Volume < MA20_vol",
        "P08_黃金交叉量增": "MA5 > MA20  AND  MA5(t-1) ≤ MA20(t-1)  AND  Volume > MA5_vol × 1.2",
        "P09_量縮後爆量紅K": "Vol(t-1,t-2,t-3) < MA20_vol × 0.6  AND  Volume > MA5_vol × 1.5  AND  Close > Open",
        "P10_組合訊號": "|Close - MA20| / MA20 < 3%  AND  RSI(14) < 50  AND  Volume < MA20_vol × 0.8  AND  Close > Open",
        "P11_多頭排列紅K": "Close > MA5 > MA10 > MA20  AND  Close > Open  AND  Volume > MA5_vol",
        "P12_多頭回檔": "MA20 ↑  AND  |Close - MA10| / MA10 < 2%  AND  Volume < MA20_vol × 0.8  AND  Close > Open",
    }
    return formulas.get(pattern_name, "N/A")


# ============================================================
# 主程式
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="價量關係分析 — 7日上漲高勝率模型")
    parser.add_argument("--train", default="2330.TW", help="訓練股票 (預設: 2330.TW)")
    parser.add_argument("--validate", nargs="+", default=["2308.TW", "2454.TW"],
                        help="驗證股票 (預設: 2308.TW 2454.TW)")
    parser.add_argument("--period", default="2y", help="歷史資料期間 (預設: 2y)")
    args = parser.parse_args()

    all_results = {}

    # 訓練集
    print(f"\n🔬 階段 1: 在 {args.train} 上發現模式")
    results_train, df_train = run_backtest(args.train, "訓練集", args.period)
    all_results[args.train] = results_train

    # 驗證集
    for i, v_stock in enumerate(args.validate, 1):
        print(f"\n🔍 階段 2.{i}: 在 {v_stock} 上驗證模式")
        results_val, df_val = run_backtest(v_stock, f"驗證集{i}", args.period)
        all_results[v_stock] = results_val

    # 推導公式
    derive_formula(all_results)

    print(f"\n✅ 分析完成！")


if __name__ == "__main__":
    main()
