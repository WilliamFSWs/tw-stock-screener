#!/usr/bin/env python3
"""
每日台股買入訊號掃描器

完整流程：
1. 取得台股前 250 大市值股票清單
2. 截取每檔股票的技術分析 K 線圖（存入 screenshots/YYYY-MM-DD/）
3. 對每檔股票計算 12 種價量模式，判斷今日是否觸發買入訊號
4. 輸出「今日推薦買入清單」+ 對應截圖

用法：
    python daily_scanner.py                          # 完整流程（截圖+掃描）
    python daily_scanner.py --scan-only              # 僅掃描，不截圖
    python daily_scanner.py --top 50                 # 只掃描前 50 大
    python daily_scanner.py --min-patterns 2         # 至少觸發 2 個模式才推薦
"""

import argparse
import json
import os
import sys
import io

# 強制將標準輸出設為 UTF-8，避免 Windows終端機 遇到 Emoji 噴出 cp950 編碼錯誤
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
import subprocess
import traceback
import warnings
import shutil
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytz
import requests
import yfinance as yf
from linebot import LineBotApi
from linebot.models import TextSendMessage, ImageSendMessage
from dotenv import load_dotenv

load_dotenv()

warnings.filterwarnings("ignore")

from pv_pattern_backtest import (
    fetch_data, add_features, ALL_PATTERNS, get_formula_description,
    calculate_win_rate_score
)


# ============================================================
# 股票清單
# ============================================================

def get_top_stocks(top_n=500):
    """取得台股前 N 大市值股票。"""
    print("📡 取得上市公司資料...")
    shares_resp = requests.get(
        "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=30, verify=False
    )
    shares_resp.raise_for_status()
    shares_data = shares_resp.json()

    shares_map = {}
    for item in shares_data:
        code = item.get("公司代號", "").strip()
        name = item.get("公司簡稱", "").strip()
        try:
            shares = int(item.get("已發行普通股數或TDR原股發行股數", "0").strip())
            if shares > 0:
                shares_map[code] = {"shares": shares, "name": name}
        except ValueError:
            continue

    print("📡 取得最新收盤價...")
    price_resp = requests.get(
        "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=30, verify=False
    )
    price_resp.raise_for_status()
    price_data = price_resp.json()

    price_map = {}
    for item in price_data:
        code = item.get("Code", "").strip()
        try:
            price_map[code] = float(item.get("ClosingPrice", "0").strip())
        except (ValueError, TypeError):
            continue

    # 計算市值排序
    stocks = []
    for code, info in shares_map.items():
        if code in price_map and price_map[code] > 0:
            cap = info["shares"] * price_map[code]
            stocks.append({
                "code": code,
                "name": info["name"],
                "market_cap": cap,
                "price": price_map[code],
            })

    stocks.sort(key=lambda x: x["market_cap"], reverse=True)
    print(f"  ✅ 取得 {len(stocks)} 檔股票，取前 {top_n} 大")
    return stocks[:top_n]


# ============================================================
# 本地 K 線圖生成 (不再依賴 Selenium)
# ============================================================

def generate_local_kline_chart(stock_id, df, output_dir, triggered_patterns):
    """
    使用 mplfinance 產生技術線圖並儲存。
    以加速 GitHub Actions 執行並避免 Selenium 崩潰。
    """
    os.makedirs(output_dir, exist_ok=True)
    safe_name = stock_id.replace(".", "_")
    output_path = os.path.join(output_dir, f"{safe_name}_kline.png")
    
    # 取最近 90 天畫圖即可
    plot_df = df.tail(90).copy()
    
    import mplfinance as mpf
    
    # 建立自訂樣式以支援中文顯示
    # 涵蓋 Windows (正黑體), Mac (蘋方), Linux (Noto Sans CJK)
    my_rc = {
        'font.family': ['Microsoft JhengHei', 'PingFang TC', 'Noto Sans CJK TC', 'Noto Sans CJK JP', 'WenQuanYi Zen Hei', 'sans-serif'],
        'axes.unicode_minus': False
    }
    my_style = mpf.make_mpf_style(base_mpf_style='yahoo', rc=my_rc)
    
    # 標記買進訊號 (最後一天)
    buy_signals = np.full(len(plot_df), np.nan)
    buy_signals[-1] = plot_df['low'].iloc[-1] * 0.98
    
    apds = [
        mpf.make_addplot(plot_df['ma5'], color='blue', width=1.0),
        mpf.make_addplot(plot_df['ma20'], color='orange', width=1.0),
        mpf.make_addplot(plot_df['ma60'], color='purple', width=1.0),
        mpf.make_addplot(buy_signals, type='scatter', markersize=200, marker='^', color='red')
    ]

    title = f"{stock_id}\nSignals: {', '.join(triggered_patterns)}"
    try:
        mpf.plot(plot_df, type='candle', volume=True, addplot=apds,
                 title=title, style=my_style, savefig=output_path, 
                 warn_too_much_data=1000, returnfig=False, closefig=True,
                 tight_layout=True, figratio=(12, 8))
        return output_path
    except Exception as e:
        print(f"  ⚠️ 產生 {stock_id} K線圖失敗: {e}")
        return None


def run_daily_scan(stocks, min_patterns=1):
    """
    對所有股票執行每日掃描 (使用批次下載優化速度)。
    """
    total = len(stocks)
    all_results = []
    errors = []
    
    # 載入優化配置
    best_patterns = []
    if os.path.exists("best_patterns_config.json"):
        with open("best_patterns_config.json", "r", encoding="utf-8") as f:
            best_patterns = json.load(f).get("best_patterns", [])
            if best_patterns:
                print(f"💡 套用近期優化配置，優先關注模式: {', '.join(best_patterns[:3])}")

    # 檢查大盤走勢 (TAIEX)
    market_mood = "未知"
    try:
        taiex = yf.Ticker("^TWII").history(period="1y")
        if not taiex.empty:
            current_price = taiex['Close'].iloc[-1]
            ma200 = taiex['Close'].rolling(window=200).mean().iloc[-1]
            ma20 = taiex['Close'].rolling(window=20).mean().iloc[-1]
            
            if current_price > ma200 and current_price > ma20:
                market_mood = "🔥 強勢多頭 (大盤站上均線)"
            elif current_price < ma200 and current_price < ma20:
                market_mood = "❄️ 弱勢熊市 (大盤跌破均線，需保守)"
            else:
                market_mood = "⚖️ 震盪整理"
    except:
        pass
        
    # 載入歷史期望值資料 (若有)
    ev_df = None
    if os.path.exists("data/stock_ev_report.csv"):
        try:
            ev_df = pd.read_csv("data/stock_ev_report.csv")
        except:
            pass
            
    # 載入原始訊號資料以計算牛熊市勝率 (若有)
    raw_df = None
    if os.path.exists("data/all_signals_raw.xlsx"):
        try:
            raw_df = pd.read_excel("data/all_signals_raw.xlsx")
            raw_df['Year'] = pd.to_datetime(raw_df['Date']).dt.year
        except:
            pass

    # [優化] 批次下載所有股票資料
    print(f"\n🚀 正在批次下載 {total} 檔股票歷史資料以加速掃描 (可能需要幾十秒)...")
    tickers = [f"{s['code']}.TW" for s in stocks]
    
    # 為了避免 yfinance 請求過大被 ban 或漏資料，分批次下載 (每批 200 檔)
    batch_size = 200
    all_history_data = {}
    
    for i in range(0, len(tickers), batch_size):
        batch_tickers = tickers[i:min(i+batch_size, len(tickers))]
        sys.stdout.write(f"\r  下載批次 {i//batch_size + 1}/{(len(tickers)-1)//batch_size + 1}...")
        sys.stdout.flush()
        
        try:
            # yf.download 回傳 multi-index dataframe if multiple tickers
            batch_str = " ".join(batch_tickers)
            bulk_df = yf.download(batch_str, period="6mo", progress=False, group_by="ticker", auto_adjust=True)
            
            # 將 multi-index 拆回各股獨立 df
            for ticker in batch_tickers:
                if len(batch_tickers) == 1:
                    stk_df = bulk_df.copy()
                else:
                    if ticker in bulk_df.columns.levels[0]:
                        stk_df = bulk_df[ticker].copy()
                    else:
                        continue
                
                stk_df = stk_df.dropna(how="all")
                if len(stk_df) > 20: # 確保資料夠多能算月線
                    stk_df = stk_df.rename(columns={
                        "Open": "open", "High": "high", "Low": "low",
                        "Close": "close", "Volume": "volume"
                    })
                    all_history_data[ticker] = add_features(stk_df)
        except Exception as e:
            print(f"  ⚠️ 批次 {i} 下載失敗: {e}")
            
    print(f"\n✅ 成功取得 {len(all_history_data)} 檔股票之歷史資料，開始進行單機運算...")

    for i, stock in enumerate(stocks, 1):
        stock_id = f"{stock['code']}.TW"
        
        # 顯示進度
        if i % 50 == 0 or i == total:
            sys.stdout.write(f"\r🔍 運算中 [{i}/{total}]")
            sys.stdout.flush()
            
        # 取得已快取的特徵資料
        df = all_history_data.get(stock_id)
        
        if df is None or df.empty:
            errors.append({"stock": stock_id, "name": stock['name'], "error": "無資料或不足"})
            continue
            
        try:
            # 檢查最後一個交易日的訊號
            last_row = df.iloc[-1]
            last_date = df.index[-1].strftime("%Y-%m-%d")

            triggered = []
            for pattern_name, pattern_func in ALL_PATTERNS.items():
                signals = pattern_func(df)
                if signals.iloc[-1]:  # 最後一天觸發
                    triggered.append(pattern_name)

            win_rate_score = calculate_win_rate_score(df)

            result = {
                "stock": stock_id,
                "name": stock['name'],
                "date": last_date,
                "close": float(last_row["close"]),
                "pct_change": float(last_row["pct_change"] * 100),
                "volume_ratio_ma5": float(last_row["vol_ratio_ma5"]),
                "volume_ratio_ma20": float(last_row["vol_ratio_ma20"]),
                "rsi14": float(last_row["rsi14"]),
                "ma20_dev": float(last_row["ma20_deviation"] * 100),
                "is_red": bool(last_row["is_red"]),
                "triggered_patterns": triggered,
                "pattern_count": len(triggered),
                "win_rate_score": win_rate_score,
                "market_mood": market_mood
            }

            # 標記是否為「近期強勢模式」
            if best_patterns:
                result["is_optimized"] = any(p in best_patterns for p in result["triggered_patterns"])
                
            # 加上期望值與歷史回測資料
            ev_stats = []
            if ev_df is not None:
                for p in result["triggered_patterns"]:
                    match = ev_df[(ev_df["Stock_ID"] == stock_id) & (ev_df["Pattern"] == p)]
                    if not match.empty:
                        stat_dict = match.iloc[0].to_dict()
                        if raw_df is not None:
                            raw_match = raw_df[(raw_df["Stock_ID"] == stock_id) & (raw_df["Pattern"] == p)]
                            if not raw_match.empty:
                                bull_years = [2021, 2023, 2024]
                                bear_years = [2022]
                                bull_signals = raw_match[raw_match['Year'].isin(bull_years)]
                                bear_signals = raw_match[raw_match['Year'].isin(bear_years)]
                                stat_dict['Bull_Win_Rate'] = (bull_signals['Is_Win'].mean() * 100) if len(bull_signals) > 0 else 0
                                stat_dict['Bear_Win_Rate'] = (bear_signals['Is_Win'].mean() * 100) if len(bear_signals) > 0 else 0
                                stat_dict['Bull_Signals'] = len(bull_signals)
                                stat_dict['Bear_Signals'] = len(bear_signals)
                        ev_stats.append(stat_dict)
            result["ev_stats"] = ev_stats
            
            all_results.append(result)
        except Exception as e:
            errors.append({"stock": stock_id, "name": stock['name'], "error": str(e)})

    print(f"\n🔍 掃描完成！共 {len(all_results)} 檔成功，{len(errors)} 檔失敗" + " " * 30)
    return all_results, errors, all_history_data


def generate_buy_report(results, min_patterns, output_dir, today_str):
    """生成今日買入訊號報告。"""
    # 篩選觸發訊號的股票
    triggered = [r for r in results if r["pattern_count"] >= min_patterns]
    # 先按勝率分數排，再按模式數
    triggered.sort(key=lambda x: (x["win_rate_score"], x["pattern_count"]), reverse=True)

    print(f"\n{'='*70}")
    print(f"📊 {today_str} 每日買入訊號報告")
    print(f"市場大盤走勢: {results[0].get('market_mood', '未知') if results else '未知'}")
    print(f"{'='*70}")
    print(f"掃描股票: {len(results)} 檔 | 最低模式數: {min_patterns}")
    print(f"觸發買入訊號: {len(triggered)} 檔")

    if not triggered:
        print(f"\n⚠️ 今日無任何股票觸發 ≥{min_patterns} 個買入模式")
        return triggered

    # 分類顯示
    # 強烈推薦（≥3 模式）
    strong = [r for r in triggered if r["pattern_count"] >= 3]
    # 推薦（2 模式）
    moderate = [r for r in triggered if r["pattern_count"] == 2]
    # 觀察（1 模式）
    watch = [r for r in triggered if r["pattern_count"] == 1]

    if strong:
        print(f"\n🔥 強烈推薦（≥3 個模式觸發）— {len(strong)} 檔：")
        print(f"{'股票':>10} {'名稱':<8} {'收盤':>8} {'漲跌%':>6} {'RSI':>5} {'量比':>5} {'模式數':>5} {'勝率分':>6} 觸發模式")
        print("-" * 95)
        for r in strong:
            patterns_str = ", ".join(r["triggered_patterns"])
            flag = "🔴" if not r["is_red"] else "🟢"
            
            # 從 ev_stats 取得最佳勝率或期望值
            best_ev = max(r.get("ev_stats", []), key=lambda x: x.get("Expected_Value(%)", -99), default={})
            ev_str = f"{best_ev.get('Expected_Value(%)', 0):>5.1f}%" if best_ev else "  N/A"
            wr_str = f"{best_ev.get('Win_Rate(%)', 0):>4.1f}%" if best_ev else " N/A"
            
            print(f"{r['stock']:>10} {r['name']:<8} {r['close']:>8.2f} "
                  f"{r['pct_change']:>+5.1f}% {r['rsi14']:>5.1f} "
                  f"{r['volume_ratio_ma20']:>5.2f} {flag}{r['pattern_count']:>4} "
                  f"EV:{ev_str} WR:{wr_str} {patterns_str}")

    if moderate:
        print(f"\n⭐ 推薦（2 個模式觸發）— {len(moderate)} 檔：")
        print(f"{'股票':>10} {'名稱':<8} {'收盤':>8} {'漲跌%':>6} {'RSI':>5} {'量比':>5} {'勝率分':>6} 觸發模式")
        print("-" * 85)
        for r in moderate:
            patterns_str = ", ".join(r["triggered_patterns"])
            best_ev = max(r.get("ev_stats", []), key=lambda x: x.get("Expected_Value(%)", -99), default={})
            ev_str = f"{best_ev.get('Expected_Value(%)', 0):>5.1f}%" if best_ev else "  N/A"
            wr_str = f"{best_ev.get('Win_Rate(%)', 0):>4.1f}%" if best_ev else " N/A"
            
            print(f"{r['stock']:>10} {r['name']:<8} {r['close']:>8.2f} "
                  f"{r['pct_change']:>+5.1f}% {r['rsi14']:>5.1f} "
                  f"{r['volume_ratio_ma20']:>5.2f} EV:{ev_str} WR:{wr_str} {patterns_str}")

    if watch and min_patterns <= 1:
        print(f"\n👀 觀察（1 個模式觸發）— {len(watch)} 檔：")
        for r in watch[:20]:  # 只顯示前 20
            print(f"  {r['stock']:>10} {r['name']:<8} {r['close']:>8.2f} "
                  f"{r['pct_change']:>+5.1f}%  {r['triggered_patterns'][0]}")
        if len(watch) > 20:
            print(f"  ... 共 {len(watch)} 檔 (僅顯示前 20)")

    # 儲存 JSON 報告
    report = {
        "date": today_str,
        "scanned": len(results),
        "triggered": len(triggered),
        "min_patterns": min_patterns,
        "strong_buy": [r for r in triggered if r["pattern_count"] >= 3],
        "buy": [r for r in triggered if r["pattern_count"] == 2],
        "watch": [r for r in triggered if r["pattern_count"] == 1],
    }
    report_path = os.path.join(output_dir, f"buy_signals_{today_str}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 報告已儲存: {report_path}")

    # 儲存 CSV
    csv_path = os.path.join(output_dir, f"buy_signals_{today_str}.csv")
    rows = []
    for r in list(triggered):
        best_ev = max(r.get("ev_stats", []), key=lambda x: x.get("Expected_Value(%)", -99), default={})
        ev_val = best_ev.get('Expected_Value(%)', 'N/A')
        wr_val = best_ev.get('Win_Rate(%)', 'N/A')
        samples_val = best_ev.get('Signals', 'N/A')
        avg_ret_val = best_ev.get('Avg_Return(%)', 'N/A')
        dd_val = best_ev.get('Max_Drawdown(%)', 'N/A')
        
        rows.append({
            "日期": r["date"],
            "股票": r["stock"],
            "名稱": r["name"],
            "收盤價": r["close"],
            "漲跌%": f"{r['pct_change']:.2f}",
            "RSI14": f"{r['rsi14']:.1f}",
            "量比MA20": f"{r['volume_ratio_ma20']:.2f}",
            "MA20偏離%": f"{r['ma20_dev']:.1f}",
            "紅K": "是" if r["is_red"] else "否",
            "模式數": r["pattern_count"],
            "觸發模式": "|".join(r["triggered_patterns"]),
            "舊版勝率評分": f"{r['win_rate_score']}%",
            "歷史樣本數": samples_val,
            "最佳勝率": f"{wr_val}%" if wr_val != 'N/A' else 'N/A',
            "最佳期望值": f"{ev_val}%" if ev_val != 'N/A' else 'N/A',
            "建議停利%": f"{avg_ret_val:.2f}%" if avg_ret_val != 'N/A' else 'N/A',
            "建議停損%": f"{dd_val:.2f}%" if dd_val != 'N/A' else 'N/A',
        })
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"💾 CSV 已儲存: {csv_path}")

    # 以期望值 (EV) 作為最終排序依據，如果是 N/A 則視為 -999，並挑出最強的
    for r in triggered:
        best_ev = max(r.get("ev_stats", []), key=lambda x: x.get("Expected_Value(%)", -99), default={})
        r["best_ev_val"] = best_ev.get("Expected_Value(%)", -999)

    triggered.sort(key=lambda x: (x["pattern_count"], x["best_ev_val"]), reverse=True)
    return triggered


# ============================================================
# LINE 通知
# ============================================================

def upload_to_imgur(image_path):
    """將本地圖片上傳到 Imgur 並獲取 URL。"""
    client_id = os.getenv("IMGUR_CLIENT_ID")
    if not client_id:
        return None
        
    url = "https://api.imgur.com/3/image"
    payload = {'type': 'base64'}
    files = [
        ('image', (os.path.basename(image_path), open(image_path, 'rb'), 'image/png'))
    ]
    headers = {
        'Authorization': f'Client-ID {client_id}'
    }
    
    try:
        response = requests.request("POST", url, headers=headers, data=payload, files=files)
        if response.status_code == 200:
            return response.json()['data']['link']
    except Exception as e:
        print(f"  ⚠️ Imgur 上傳失敗: {e}")
    return None


def send_line_notification(results, today_str):
    """將今日買入訊號發送到 LINE。"""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.getenv("LINE_USER_ID")
    
    if not token or not user_id:
        print("⚠️ 找不到 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_ID，跳過 LINE 通知。")
        return

    line_bot_api = LineBotApi(token)
    
    triggered = [r for r in results if r["pattern_count"] >= 2]
    
    for r in triggered:
        best_ev = max(r.get("ev_stats", []), key=lambda x: x.get("Expected_Value(%)", -99), default={})
        r["best_ev_val"] = best_ev.get("Expected_Value(%)", -999)
    triggered.sort(key=lambda x: (x["pattern_count"], x["best_ev_val"]), reverse=True)
    
    market_mood = results[0].get("market_mood", "未知") if results else "未知"
    
    if not triggered:
        msg = f"📅 {today_str} 台股掃描完成\n大盤走勢: {market_mood}\n今日無觸發強烈推薦訊號。"
        line_bot_api.push_message(user_id, TextSendMessage(text=msg))
        return

    # 彙總強烈推薦
    strong = [r for r in triggered if r["pattern_count"] >= 3]
    moderate = [r for r in triggered if r["pattern_count"] == 2]
    
    msg = f"📅 {today_str} 台股買入訊號報告\n"
    msg += f"大盤走勢: {market_mood}\n"
    msg += f"--------------------\n"
    
    def format_stock_msg(r):
        patterns = ", ".join(r['triggered_patterns'])
        ev_stats = r.get("ev_stats", [])
        if ev_stats:
            best = max(ev_stats, key=lambda x: x.get("Expected_Value(%)", -99))
            wr = best.get("Win_Rate(%)", 0)
            avg_ret = best.get("Avg_Return(%)", 0)
            dd = best.get("Max_Drawdown(%)", -7)
            ev = best.get("Expected_Value(%)", 0)
            signals = best.get("Total_Signals", 0)
            
            s = f"📌 {r['stock']} {r['name']} (收 {r['close']})\n"
            s += f"  💡 模式: {patterns}\n"
            s += f"  📊 歷史勝率: {wr}% (樣本: {signals}次), 期望值: {ev}%\n"
            s += f"  🎯 建議:\n"
            s += f"   - 進場: 隔日開盤或拉回 -2% 內接刀\n"
            s += f"   - 停損: 跌破進場價 {dd:.2f}% 即出\n"
            s += f"   - 停利: 若站穩 5% 即分批出場, 最高可看 {avg_ret:.2f}%\n"
            return s
        else:
            return f"📌 {r['stock']} {r['name']} (收 {r['close']})\n  💡 模式: {patterns}\n  ⚠️ 缺乏歷史回測資料\n"
    
    if strong:
        msg += f"🔥 強烈推薦 (≥3個模式): {len(strong)} 檔\n"
        for r in strong[:3]:
            msg += format_stock_msg(r) + "\n"
    elif moderate:
        msg += f"⭐ 推薦 (2個模式): {len(moderate)} 檔\n"
        for r in moderate[:3]:
            msg += format_stock_msg(r) + "\n"
    
    msg += f"--------------------\n"
    msg += "💡 詳細報告與 K 線圖請見 Google Drive。"

    # 發送文字訊息
    line_bot_api.push_message(user_id, TextSendMessage(text=msg))
    print("✅ LINE 摘要通知已發送")

    # 發送截圖 (強烈推薦的前 3 檔)
    imgur_client_id = os.getenv("IMGUR_CLIENT_ID")
    if imgur_client_id and strong:
        print("📸 正在上傳截圖到 Imgur 並發送到 LINE...")
        screenshot_dir = os.path.join("screenshots", today_str)
        for r in strong[:3]:
            safe_code = r["stock"].replace(".", "_")
            img_path = os.path.join(screenshot_dir, f"{safe_code}_kline.png")
            
            if os.path.exists(img_path):
                img_url = upload_to_imgur(img_path)
                if img_url:
                    line_bot_api.push_message(user_id, ImageSendMessage(
                        original_content_url=img_url,
                        preview_image_url=img_url
                    ))
                    print(f"  ✅ 已發送 {r['stock']} 截圖")


# ============================================================
# 主程式
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="每日台股買入訊號掃描器"
    )
    parser.add_argument("--top", "-n", type=int, default=500,
                        help="掃描前 N 大市值 (預設: 500)")
    parser.add_argument("--min-patterns", "-m", type=int, default=1,
                        help="至少觸發幾個模式才推薦 (預設: 1)")
    parser.add_argument("--scan-only", action="store_true",
                        help="僅掃描，不截圖")
    parser.add_argument("--screenshot-only", action="store_true",
                        help="僅截圖，不掃描")
    parser.add_argument("--output-dir", "-o", default="./daily_reports",
                        help="報告輸出目錄 (預設: ./daily_reports)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="截圖間隔秒數 (預設: 2.0)")
    parser.add_argument("--max-charts", type=int, default=200,
                        help="最多產生幾張技術線圖 (預設: 200)")

    args = parser.parse_args()

    # 今日日期
    tw_tz = pytz.timezone("Asia/Taipei")
    today = datetime.now(tw_tz)
    today_str = today.strftime("%Y-%m-%d")

    print(f"{'='*70}")
    print(f"📅 每日台股買入訊號掃描器 — {today_str}")
    print(f"{'='*70}")

    # 報告目錄
    os.makedirs(args.output_dir, exist_ok=True)

    # 取得股票清單
    stocks = get_top_stocks(args.top)

    # 1. 掃描訊號
    print(f"\n🔬 開始掃描買入訊號...")
    results, errors, all_history_data = run_daily_scan(stocks, args.min_patterns)

    # 2. 生成報告 (找出觸發訊號的股票)
    triggered = generate_buy_report(results, args.min_patterns, args.output_dir, today_str)

    # 3. 截圖 (對所有強烈推薦或推薦的股票進行截圖，並合併為 PDF)
    if not args.scan_only:
        top_picks = [r for r in triggered if r["pattern_count"] >= 2]
        # 限制最大截圖數量
        top_picks = top_picks[:args.max_charts]
        
        if top_picks:
            screenshot_dir = os.path.join("screenshots", today_str)
            print(f"\n📸 對 {len(top_picks)} 檔最強訊號的股票進行截圖並合併為 PDF...")
            
            generated_images = []
            for r in top_picks:
                stock_id = r["stock"]
                df = all_history_data.get(stock_id)
                if df is not None and not df.empty:
                    img_path = generate_local_kline_chart(stock_id, df, screenshot_dir, r['triggered_patterns'])
                    if img_path:
                        generated_images.append(img_path)
            
            # 合併為 PDF
            if generated_images:
                try:
                    from PIL import Image
                    pdf_path = os.path.join(args.output_dir, f"Daily_Klines_{today_str}.pdf")
                    
                    # 讀取第一張圖片並轉換為 RGB (PDF 需要 RGB 模式)
                    first_image = Image.open(generated_images[0]).convert('RGB')
                    
                    # 讀取剩餘圖片並轉換為 RGB
                    other_images = []
                    for img_path in generated_images[1:]:
                        img = Image.open(img_path).convert('RGB')
                        other_images.append(img)
                        
                    # 儲存為 PDF
                    first_image.save(pdf_path, save_all=True, append_images=other_images)
                    print(f"  📄 成功合併 {len(generated_images)} 張圖表至 PDF: {pdf_path}")
                except Exception as e:
                    print(f"  ⚠️ 合併 PDF 失敗: {e}")
        else:
            print("\n📸 今日無推薦訊號，跳過截圖與 PDF 產生。")

        if args.screenshot_only:
            print(f"\n✅ 截圖完成！")
            return

    # 4. 發送 LINE 通知
    if not args.screenshot_only:
        send_line_notification(results, today_str)

    # 顯示對應截圖位置
    if not args.scan_only and top_picks:
        pdf_path = os.path.join(args.output_dir, f"Daily_Klines_{today_str}.pdf")
        if os.path.exists(pdf_path):
            print(f"\n📸 本日 K 線圖彙總報告：\n  ✅ {pdf_path}")

    print(f"\n✅ 掃描完成！")
    print(f"   推薦買入: {len([t for t in triggered if t['pattern_count'] >= 2])} 檔")
    print(f"   觀察名單: {len([t for t in triggered if t['pattern_count'] == 1])} 檔")


    # 清理舊截圖以節省空間
    print("\n🧹 清理 7 天前的舊截圖資料夾...")
    try:
        if os.path.exists("screenshots"):
            import shutil
            now = time.time()
            for dir_name in os.listdir("screenshots"):
                dir_path = os.path.join("screenshots", dir_name)
                if os.path.isdir(dir_path):
                    # 檢查資料夾建立時間，超過 7 天 (7*86400 秒) 則刪除
                    if os.stat(dir_path).st_mtime < now - 7 * 86400:
                        shutil.rmtree(dir_path)
                        print(f"   🗑️ 已刪除過期截圖: {dir_name}")
    except Exception as e:
        print(f"   ⚠️ 清理舊截圖失敗: {e}")


if __name__ == "__main__":
    main()
