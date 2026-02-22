# 台股技術線型自動篩選系統

這是一個使用 Python 開發的輕量級台股看盤機器人。系統會在台股開盤期間 (09:00 - 13:30)，自動抓取指定台灣 50 權值股成分股的股價資料，並透過技術指標（RSI、MACD、布林通道）計算出「強烈買進 / 強烈賣出」的個股。若有符合條件，將會自動透過 **Line Notify** 發送推播通知到您的手機！

## 功能特色

- **完全免費**: 使用 Yahoo Finance 免費 API 讀取資料。
- **全自動排程**: 內建 Python `schedule` 模組，不需要複雜的伺服器設定。
- **即時通知**: 整合 Line Notify 推播機制，不錯過任何潛在機會。
- **客製化名單**: 可以在 `main.py` 自由修改 `TARGET_STOCKS` 加入您自己的自選股。

## 🚀 第一步：取得您的 Line Notify 權杖 (Token)

在執行程式之前，請先確保您有一組 Line Notify token，程式才知道要把訊息發送到哪個群組/聯絡人。

1. 進入 [LINE Notify 官方網站](https://notify-bot.line.me/zh_TW/) 並點選右上角登入您的 Line 帳號。
2. 登入後，點選右上角您的用戶名稱，選擇 **「個人頁面」**。
3. 往下捲動找到「發行存取權杖 (Developer)」區塊，點選 **「發行權杖」**。
4. 在彈出視窗中：
   - 填寫權杖名稱 (例如：`股市雷達`)，這將會是通知訊息的標題。
   - 選擇要接收通知的聊天室 (可以選擇 `透過1對1聊天接收LINE Notify的通知`)。
   - 點選「發行」。
5. **重要：** 網頁會顯示一長串英文數字的權杖。請務必**立刻複製**它 (離開畫面後就無法再看到了)。

## ⚙️ 第二步：設定專案

1. 開啟本專案資料夾下的 `.env` 檔案。
2. 將剛才複製的 Token 貼上並替換原本的提示字：
   ```env
   LINE_TOKEN=這裡貼上您剛剛複製的權杖字串
   ```
3. 存檔退出。

## ▶️ 第三步：如何執行系統

### 方法 1. 在 Mac 終端機執行 (最簡單)

打開 Mac 的「終端機 (Terminal)」應用程式，複製並貼上以下指令：

```bash
cd /Users/william/Documents/tw-stock-screener
source venv/bin/activate
python main.py
```

按下 Enter 後，您會看到如下畫面：
> `啟動台股技術線型篩選系統 - 現在時間...`
> `排程已設定。按下 Ctrl+C 結束。`

此時，**只要您不關閉這個終端機視窗**，系統就會在每天盤中每小時自動幫您掃描股票。若想結束程式，可以隨時在該視窗按下鍵盤的 `Ctrl + C`。

### 方法 2. 在背景自動執行

如果您不希望一直開著終端機視窗，也可以使用 Mac 內建的 `crontab` 來設定自動執行腳本。

---

## ☁️ 方案 B：使用 GitHub Actions 免電腦執行 (推薦)

如果您不想讓電腦開著，且本機環境有區域網路連線限制，這是最完美的解決方案。

### 1. 建立 GitHub 儲存庫 (Repository)
1. 登入您的 GitHub 帳號。
2. 點選 **New** 建立一個新的儲存庫，名稱自訂 (例如 `my-stock-screener`)。
3. 建議設為 **Private** (私有)，以保護您的選股邏輯與 API 資訊。

### 2. 設定 Line Token 密鑰 (Secrets)
1. 在您的 GitHub 儲存庫頁面，點選上方標籤的 **Settings**。
2. 在左側選單找到 **Secrets and variables** -> **Actions**。
3. 點選 **New repository secret**。
4. Name 填入：`LINE_TOKEN`。
5. Secret 填入：您的 Line Notify Token 字串。
6. 點選 **Add secret**。

### 3. 上傳程式碼
將包含 `.github/workflows/` 資料夾在內的所有檔案上傳到該儲存庫。

### 4. 啟動排程
1. 點選儲存庫上方的 **Actions** 標籤。
2. 由於我們已經寫好了 `.github/workflows/stock_screener.yml`，您會看到左側有專案名稱。
3. 點選該工作流，您可以點選 **Run workflow** 手動測試一次。
4. 測試成功後，GitHub 就會依照設定的定時時間（台股盤中每小時）自動為您執行並發送 Line 通知！

