# 台股技術線型自動篩選與每日掃描系統

由 AI 驅動的台股自動化分析與掃描系統。包含 12 種價量模式回測、每日熱門股掃描、K 線截圖推送與 LINE 整合。

## ✨ 主要功能

1. **每日自動掃描** (`daily_scanner.py`): 自動篩選前 250 大市值股票，找出今日觸發買入訊號的標的。
2. **價量模式回測** (`pv_pattern_backtest.py`): 定義 12 種高勝率價量公式（如：長下影線放量、量增紅K、價量背離等）。
3. **自動截動圖** (`stock_screenshot.py`): 自動截取 Yahoo 股市技術分析頁面的日 K 線圖。
4. **LINE 通知**: 每日將掃描結果與 K 線圖推送到您的 LINE 手機。
5. **GitHub Actions 整合**: 全自動排程，每天開盤前與收盤後自動執行。

## 🚀 快速開始

### 1. 安裝與執行 (本地)

```bash
# 安裝依賴
pip install -r requirements.txt

# 執行每日掃描 (掃描前 250 大，至少觸發 2 個模式才推薦)
python daily_scanner.py --top 250 --min-patterns 2
```

### 2. GitHub Actions 自動化設定 (免電腦執行)

1. **上傳程式碼**: 將此專案上傳至您的 GitHub Repository (`WilliamFSWs/tw-stock-screener`)。
2. **Secrets 設定**: 在 GitHub Repository -> Settings -> Secrets and variables -> Actions 中新增：
   - `LINE_CHANNEL_ACCESS_TOKEN`: LINE 存取權限 Token
   - `LINE_USER_ID`: 您的 LINE User ID
   - `IMGUR_CLIENT_ID`: (建議) 申請 [Imgur Client ID](https://api.imgur.com/oauth2/addclient) 以便手機接收截圖。
3. **啟動**: 程式會在每天 **09:05 (開盤前)** 與 **15:30 (收盤後)** 自動執行。

## 📊 回測成果

根據對台積電、台達電、聯發科等多檔股票的驗證，特定模式在 7 日內最高價勝率達到 **90% 以上**。
細節請參閱 `screenshots/backtest_report.csv`。

## 🛠️ 腳本清單

- `daily_scanner.py`: **每日掃描主程式 (核心)**
- `pv_pattern_backtest.py`: 價量關係回測與 12 種模式定義
- `stock_screenshot.py`: 單檔 K 線截圖模組 (Selenium)
- `batch_screenshot_top250.py`: 市值排名與批量截圖
- `backtest_all_screenshots.py`: 對所有已截圖股票進行批量回測分析
- `app.py`: LINE Bot Webhook 處理器
