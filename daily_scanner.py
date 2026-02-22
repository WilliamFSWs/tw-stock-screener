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
import time
import traceback
import warnings
from datetime import datetime

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
)


# ============================================================
# 股票清單
# ============================================================

def get_top_stocks(top_n=250):
    """取得台股前 N 大市值股票。"""
    print("📡 取得上市公司資料...")
    shares_resp = requests.get(
        "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=30
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
        "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=30
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
# 截圖（呼叫 stock_screenshot.py）
# ============================================================

def screenshot_stocks(stock_codes, output_dir, delay=2.0):
    """批量截取股票 K 線圖。"""
    from stock_screenshot import create_driver, screenshot_stock

    os.makedirs(output_dir, exist_ok=True)
    progress_file = os.path.join(output_dir, ".progress.json")

    # 載入進度
    completed = set()
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            completed = set(json.load(f))

    remaining = [c for c in stock_codes if c.replace(".TW", "") not in completed]
    if not remaining:
        print(f"  ✅ 所有截圖已完成")
        return

    print(f"📸 截取 K 線圖: {len(remaining)} 檔待處理...")
    driver = create_driver()

    try:
        for i, stock_id in enumerate(remaining, 1):
            try:
                screenshot_stock(driver, stock_id, output_dir)
                completed.add(stock_id.replace(".TW", ""))
                with open(progress_file, "w") as f:
                    json.dump(list(completed), f)
            except Exception as e:
                print(f"  ⚠️ {stock_id} 截圖失敗: {e}")
                try:
                    driver.quit()
                except:
                    pass
                driver = create_driver()

            if i < len(remaining):
                time.sleep(delay)
    except KeyboardInterrupt:
        print(f"\n⚠️ 中斷，已完成 {len(completed)} 檔（可用 --resume 繼續）")
    finally:
        try:
            driver.quit()
        except:
            pass


# ============================================================
# 訊號掃描
# ============================================================

def scan_today_signals(stock_id, stock_name=""):
    """
    掃描單檔股票今日是否觸發買入訊號。

    Returns:
        dict: 包含觸發的模式列表和詳細資訊
    """
    try:
        df = fetch_data(stock_id, period="6mo")
        df = add_features(df)
    except Exception as e:
        return {"stock": stock_id, "name": stock_name, "error": str(e)}

    if df.empty:
        return {"stock": stock_id, "name": stock_name, "error": "無資料"}

    # 檢查最後一個交易日的訊號
    last_row = df.iloc[-1]
    last_date = df.index[-1].strftime("%Y-%m-%d")

    triggered = []
    for pattern_name, pattern_func in ALL_PATTERNS.items():
        signals = pattern_func(df)
        if signals.iloc[-1]:  # 最後一天觸發
            triggered.append(pattern_name)

    # 取得關鍵指標
    info = {
        "stock": stock_id,
        "name": stock_name,
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
    }
    return info


def run_daily_scan(stocks, min_patterns=1):
    """
    對所有股票執行每日掃描。

    Args:
        stocks: 股票清單 [{"code": "2330", "name": "台積電", ...}, ...]
        min_patterns: 至少觸發幾個模式才列入推薦

    Returns:
        list: 觸發訊號的股票列表
    """
    total = len(stocks)
    all_results = []
    errors = []

    for i, stock in enumerate(stocks, 1):
        stock_id = f"{stock['code']}.TW"
        sys.stdout.write(f"\r🔍 掃描中 [{i}/{total}] {stock_id} {stock['name']:<8}")
        sys.stdout.flush()

        result = scan_today_signals(stock_id, stock['name'])
        if "error" in result:
            errors.append(result)
        else:
            all_results.append(result)

        # API rate limit
        if i % 5 == 0:
            time.sleep(0.5)

    print(f"\r🔍 掃描完成！共 {len(all_results)} 檔成功，{len(errors)} 檔失敗" + " " * 30)
    return all_results, errors


def generate_buy_report(results, min_patterns, output_dir, today_str):
    """生成今日買入訊號報告。"""
    # 篩選觸發訊號的股票
    triggered = [r for r in results if r["pattern_count"] >= min_patterns]
    triggered.sort(key=lambda x: x["pattern_count"], reverse=True)

    print(f"\n{'='*70}")
    print(f"📊 {today_str} 每日買入訊號報告")
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
        print(f"{'股票':>10} {'名稱':<8} {'收盤':>8} {'漲跌%':>6} {'RSI':>5} {'量比':>5} {'模式數':>5} 觸發模式")
        print("-" * 85)
        for r in strong:
            patterns_str = ", ".join(r["triggered_patterns"])
            flag = "🔴" if not r["is_red"] else "🟢"
            print(f"{r['stock']:>10} {r['name']:<8} {r['close']:>8.2f} "
                  f"{r['pct_change']:>+5.1f}% {r['rsi14']:>5.1f} "
                  f"{r['volume_ratio_ma20']:>5.2f} {flag}{r['pattern_count']:>4} "
                  f"{patterns_str}")

    if moderate:
        print(f"\n⭐ 推薦（2 個模式觸發）— {len(moderate)} 檔：")
        print(f"{'股票':>10} {'名稱':<8} {'收盤':>8} {'漲跌%':>6} {'RSI':>5} {'量比':>5} 觸發模式")
        print("-" * 75)
        for r in moderate:
            patterns_str = ", ".join(r["triggered_patterns"])
            print(f"{r['stock']:>10} {r['name']:<8} {r['close']:>8.2f} "
                  f"{r['pct_change']:>+5.1f}% {r['rsi14']:>5.1f} "
                  f"{r['volume_ratio_ma20']:>5.2f} {patterns_str}")

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
    for r in triggered:
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
        })
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"💾 CSV 已儲存: {csv_path}")

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
    if not triggered:
        msg = f"📅 {today_str} 台股掃描完成\n今日無觸發強烈推薦訊號。"
        line_bot_api.push_message(user_id, TextSendMessage(text=msg))
        return

    # 彙總強烈推薦
    strong = [r for r in triggered if r["pattern_count"] >= 3]
    moderate = [r for r in triggered if r["pattern_count"] == 2]
    
    msg = f"📅 {today_str} 台股買入訊號報告\n"
    msg += f"--------------------\n"
    msg += f"🔥 強烈推薦: {len(strong)} 檔\n"
    for r in strong[:5]:
        msg += f"• {r['stock']} {r['name']} ({r['pattern_count']}模式)\n"
    
    msg += f"\n⭐ 推薦: {len(moderate)} 檔\n"
    for r in moderate[:5]:
        msg += f"• {r['stock']} {r['name']}\n"
    
    if len(triggered) > 10:
        msg += f"...\n(共 {len(triggered)} 檔觸發訊號)"
    
    msg += f"\n--------------------\n"
    msg += "💡 詳細報表請見 GitHub Artifacts。"

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
    parser.add_argument("--top", "-n", type=int, default=250,
                        help="掃描前 N 大市值 (預設: 250)")
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

    # 截圖
    if not args.scan_only:
        screenshot_dir = os.path.join("screenshots", today_str)
        stock_ids = [f"{s['code']}.TW" for s in stocks]
        screenshot_stocks(stock_ids, screenshot_dir, delay=args.delay)

        if args.screenshot_only:
            print(f"\n✅ 截圖完成！儲存於: {screenshot_dir}")
            return

    # 掃描訊號
    print(f"\n🔬 開始掃描買入訊號...")
    results, errors = run_daily_scan(stocks, args.min_patterns)

    # 生成報告
    triggered = generate_buy_report(results, args.min_patterns, args.output_dir, today_str)

    # 發送 LINE 通知
    if not args.screenshot_only:
        send_line_notification(results, today_str)

    # 顯示對應截圖位置
    if not args.scan_only and triggered:
        screenshot_dir = os.path.join("screenshots", today_str)
        print(f"\n📸 對應截圖位置:")
        for r in [t for t in triggered if t["pattern_count"] >= 2][:10]:
            code = r["stock"].replace(".TW", "_TW")
            img = os.path.join(screenshot_dir, f"{code}_kline.png")
            exists = "✅" if os.path.exists(img) else "❌"
            print(f"  {exists} {r['stock']} → {img}")

    print(f"\n✅ 掃描完成！")
    print(f"   推薦買入: {len([t for t in triggered if t['pattern_count'] >= 2])} 檔")
    print(f"   觀察名單: {len([t for t in triggered if t['pattern_count'] == 1])} 檔")


if __name__ == "__main__":
    main()
