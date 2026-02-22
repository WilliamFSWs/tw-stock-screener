#!/usr/bin/env python3
"""
Yahoo 台股技術線圖截圖工具
自動截取 Yahoo 奇摩股市技術分析頁面的日 K 線圖與成交量區域。
支持批量截取多檔股票。

用法：
    python stock_screenshot.py 2330.TW 2317.TW 0050.TW
    python stock_screenshot.py 2330.TW --output-dir ./screenshots
"""

import argparse
import os
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


def create_driver():
    """建立 Chrome headless 瀏覽器實例。"""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1200")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=zh-TW")
    # 避免被偵測為自動化工具
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def dismiss_popups(driver):
    """關閉可能出現的彈窗（cookie 同意、廣告等）。"""
    popup_selectors = [
        # Yahoo cookie 同意按鈕
        "button.btn.primary",
        "[name='agree']",
        ".consent-overlay button",
        # 常見的關閉按鈕
        "button[aria-label='close']",
        "button[aria-label='Close']",
    ]
    for selector in popup_selectors:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            btn.click()
            time.sleep(0.5)
        except (NoSuchElementException, Exception):
            pass


def screenshot_stock(driver, stock_id, output_dir):
    """
    截取單檔股票的技術分析 K 線圖 + 成交量。

    Args:
        driver: Selenium WebDriver 實例
        stock_id: 股票代號，如 '2330.TW'
        output_dir: 輸出目錄路徑

    Returns:
        str: 截圖檔案路徑，失敗時返回 None
    """
    url = f"https://tw.stock.yahoo.com/quote/{stock_id}/technical-analysis"
    print(f"📈 正在載入 {stock_id} 技術分析頁面...")
    driver.get(url)

    # 等待頁面基本載入
    time.sleep(3)

    # 嘗試關閉彈窗
    dismiss_popups(driver)

    # 等待圖表載入完成
    chart_selectors = [
        # Yahoo 技術分析圖表的可能容器
        "div.chart-container",
        "#chart-container",
        ".technical-chart",
        "div[data-test='chart-container']",
        # 通用的 canvas / svg 圖表元素
        ".chart-canvas-container",
        "div.canvasContainer",
    ]

    chart_element = None

    # 嘗試多種 selector 來定位圖表
    for selector in chart_selectors:
        try:
            chart_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            print(f"  ✅ 找到圖表元素: {selector}")
            break
        except TimeoutException:
            continue

    # 構建輸出檔名
    safe_name = stock_id.replace(".", "_")
    output_path = os.path.join(output_dir, f"{safe_name}_kline.png")

    if chart_element:
        # 滾動到圖表位置確保可見
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", chart_element)
        time.sleep(1)

        # 截取圖表元素
        try:
            chart_element.screenshot(output_path)
            print(f"  💾 圖表截圖已儲存: {output_path}")
            return output_path
        except Exception as e:
            print(f"  ⚠️ 元素截圖失敗 ({e})，改用整頁截圖...")

    # Fallback：嘗試找到包含圖表的更大區域
    # Yahoo 技術分析頁面的圖表通常在頁面中段
    print(f"  ℹ️ 未能精確定位圖表元素，嘗試截取主要內容區域...")

    # 嘗試找到頁面主內容區域
    content_selectors = [
        "#main-content",
        "main",
        ".main-content",
        "#YDC-Col1",
        "section.main-section",
    ]

    for selector in content_selectors:
        try:
            content = driver.find_element(By.CSS_SELECTOR, selector)
            driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", content)
            time.sleep(1)
            content.screenshot(output_path)
            print(f"  💾 內容區截圖已儲存: {output_path}")
            return output_path
        except (NoSuchElementException, Exception):
            continue

    # 最後 fallback：截取整頁
    driver.save_screenshot(output_path)
    print(f"  💾 整頁截圖已儲存: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Yahoo 台股技術線圖截圖工具 — 自動截取日 K 線圖與成交量"
    )
    parser.add_argument(
        "stocks",
        nargs="+",
        help="股票代號列表，例如：2330.TW 2317.TW 0050.TW",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="./screenshots",
        help="截圖輸出目錄 (預設: ./screenshots)",
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=2.0,
        help="每檔股票之間的等待秒數 (預設: 2.0)",
    )

    args = parser.parse_args()

    # 建立輸出目錄
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 截圖將儲存至: {output_dir}\n")

    # 建立瀏覽器
    print("🚀 正在啟動 Chrome 瀏覽器...")
    driver = create_driver()

    results = []
    try:
        for i, stock_id in enumerate(args.stocks):
            if i > 0:
                time.sleep(args.delay)

            result = screenshot_stock(driver, stock_id, output_dir)
            results.append((stock_id, result))

    finally:
        driver.quit()
        print("\n🏁 瀏覽器已關閉")

    # 輸出結果摘要
    print("\n" + "=" * 50)
    print("📊 截圖結果摘要：")
    print("=" * 50)
    success = 0
    for stock_id, path in results:
        if path:
            print(f"  ✅ {stock_id} → {path}")
            success += 1
        else:
            print(f"  ❌ {stock_id} → 截圖失敗")

    print(f"\n共 {len(results)} 檔，成功 {success} 檔，失敗 {len(results) - success} 檔")


if __name__ == "__main__":
    main()
