#!/usr/bin/env python3
"""
批量截取台股前 250 大市值股票的技術分析 K 線圖。

流程：
1. 從 TWSE OpenData API 取得上市公司已發行股數
2. 從 TWSE 每日收盤行情取得最新收盤價
3. 計算市值 = 收盤價 × 已發行股數
4. 取前 250 大
5. 用 Selenium 逐一截取 Yahoo 奇摩技術分析頁面

用法：
    python batch_screenshot_top250.py
    python batch_screenshot_top250.py --top 50 --output-dir ./screenshots
    python batch_screenshot_top250.py --resume   # 從上次中斷處繼續
"""

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

import requests

# 匯入截圖工具
from stock_screenshot import create_driver, screenshot_stock


def fetch_shares_outstanding():
    """從 TWSE OpenData API 取得所有上市公司的已發行股數。"""
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    print("📡 正在取得上市公司基本資料...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    shares_map = {}
    for item in data:
        code = item.get("公司代號", "").strip()
        shares_str = item.get("已發行普通股數或TDR原股發行股數", "0").strip()
        try:
            shares = int(shares_str)
            if shares > 0:
                shares_map[code] = {
                    "shares": shares,
                    "name": item.get("公司簡稱", "").strip(),
                }
        except ValueError:
            continue

    print(f"  ✅ 取得 {len(shares_map)} 家上市公司資料")
    return shares_map


def fetch_daily_prices():
    """從 TWSE 取得最新每日收盤行情。"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    print("📡 正在取得最新收盤價...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    price_map = {}
    for item in data:
        code = item.get("Code", "").strip()
        close_str = item.get("ClosingPrice", "").strip()
        try:
            close_price = float(close_str)
            if close_price > 0:
                price_map[code] = close_price
        except (ValueError, TypeError):
            continue

    print(f"  ✅ 取得 {len(price_map)} 檔股票收盤價")
    return price_map


def get_top_stocks(top_n=250):
    """計算並返回前 N 大市值股票列表。"""
    shares_map = fetch_shares_outstanding()
    price_map = fetch_daily_prices()

    # 計算市值
    market_caps = []
    for code, info in shares_map.items():
        if code in price_map:
            market_cap = info["shares"] * price_map[code]
            market_caps.append({
                "code": code,
                "name": info["name"],
                "market_cap": market_cap,
                "price": price_map[code],
                "shares": info["shares"],
            })

    # 按市值排序
    market_caps.sort(key=lambda x: x["market_cap"], reverse=True)

    # 取前 N 大
    top_stocks = market_caps[:top_n]

    print(f"\n📊 台股前 {top_n} 大市值股票：")
    print(f"{'排名':>4} {'代號':>6} {'名稱':<8} {'市值(億元)':>12} {'收盤價':>8}")
    print("-" * 50)
    for i, stock in enumerate(top_stocks[:10], 1):
        cap_yi = stock["market_cap"] / 1e8  # 轉為億元
        print(f"{i:>4} {stock['code']:>6} {stock['name']:<8} {cap_yi:>12,.0f} {stock['price']:>8.2f}")
    if len(top_stocks) > 10:
        print(f"  ... 共 {len(top_stocks)} 檔 (僅顯示前 10)")

    return top_stocks


def load_progress(progress_file):
    """載入截圖進度。"""
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            return set(json.load(f))
    return set()


def save_progress(progress_file, completed):
    """儲存截圖進度。"""
    with open(progress_file, "w") as f:
        json.dump(list(completed), f)


def main():
    parser = argparse.ArgumentParser(
        description="批量截取台股前 N 大市值股票的技術分析 K 線圖"
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=250,
        help="截取前 N 大市值股票 (預設: 250)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./screenshots",
        help="截圖輸出目錄 (預設: ./screenshots)",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=2.0,
        help="每檔股票之間的等待秒數 (預設: 2.0)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="從上次中斷處繼續截圖",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="僅列出股票清單，不截圖",
    )

    args = parser.parse_args()

    # 取得前 N 大市值股票
    top_stocks = get_top_stocks(args.top)

    if args.list_only:
        print(f"\n完整清單：")
        for i, stock in enumerate(top_stocks, 1):
            cap_yi = stock["market_cap"] / 1e8
            print(f"{i:>4}. {stock['code']} {stock['name']:<8} 市值 {cap_yi:>10,.0f} 億")
        return

    # 建立輸出目錄
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n📁 截圖將儲存至: {output_dir}")

    # 載入進度
    progress_file = os.path.join(output_dir, ".progress.json")
    completed = load_progress(progress_file) if args.resume else set()

    if completed:
        print(f"📂 找到先前進度: 已完成 {len(completed)} 檔")

    # 過濾已完成的
    remaining = [s for s in top_stocks if s["code"] not in completed]
    print(f"📋 待截取: {len(remaining)} 檔\n")

    if not remaining:
        print("✅ 所有股票已截取完成！")
        return

    # 啟動瀏覽器
    print("🚀 正在啟動 Chrome 瀏覽器...")
    driver = create_driver()

    success_count = 0
    fail_count = 0
    failed_stocks = []

    try:
        for i, stock in enumerate(remaining, 1):
            stock_id = f"{stock['code']}.TW"
            print(f"\n[{i}/{len(remaining)}] {stock_id} {stock['name']}")

            try:
                result = screenshot_stock(driver, stock_id, output_dir)
                if result:
                    success_count += 1
                    completed.add(stock["code"])
                    save_progress(progress_file, completed)
                else:
                    fail_count += 1
                    failed_stocks.append(stock_id)
            except Exception as e:
                fail_count += 1
                failed_stocks.append(stock_id)
                print(f"  ❌ 錯誤: {e}")
                traceback.print_exc()

                # 嘗試重新建立瀏覽器
                try:
                    driver.quit()
                except:
                    pass
                print("  🔄 重新啟動瀏覽器...")
                driver = create_driver()

            # 等待
            if i < len(remaining):
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print(f"\n\n⚠️ 使用者中斷！已完成 {success_count} 檔")
        print("💡 使用 --resume 參數可從中斷處繼續")
    finally:
        try:
            driver.quit()
        except:
            pass
        save_progress(progress_file, completed)
        print("\n🏁 瀏覽器已關閉")

    # 結果摘要
    print("\n" + "=" * 50)
    print("📊 批量截圖結果摘要：")
    print("=" * 50)
    print(f"  ✅ 成功: {success_count} 檔")
    print(f"  ❌ 失敗: {fail_count} 檔")
    print(f"  📂 總完成: {len(completed)}/{len(top_stocks)} 檔")

    if failed_stocks:
        print(f"\n失敗清單：")
        for s in failed_stocks:
            print(f"  - {s}")
        print(f"\n💡 可使用以下命令重新截取失敗的股票：")
        print(f"  python stock_screenshot.py {' '.join(failed_stocks)}")


if __name__ == "__main__":
    main()
