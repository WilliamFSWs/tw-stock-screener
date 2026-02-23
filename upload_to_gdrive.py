import os
import json
import base64
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 設定要上傳的目標雲端資料夾 ID (從網址列可以拿到的那一串)
TARGET_FOLDER_ID = "1KWZHVnpqkDoyTin9iFABLdfBw9XjpmRS"

def get_gdrive_service():
    """初始化並回傳 Google Drive API 服務物件"""
    # 從環境變數中取得 Base64 編碼的 Service Account Credentials
    creds_b64 = os.getenv("GCP_CREDENTIALS_B64")
    if not creds_b64:
        print("⚠️ 找不到環境變數 GCP_CREDENTIALS_B64，略過 Google Drive 上傳。")
        return None
        
    try:
        # 將 Base64 解碼回 JSON 字串，並載入憑證
        creds_json = base64.b64decode(creds_b64).decode('utf-8')
        creds_dict = json.loads(creds_json)
        
        scopes = ['https://www.googleapis.com/auth/drive.file']
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        print(f"⚠️ 初始化 Google Drive 服務失敗: {e}")
        return None

def create_folder(service, folder_name, parent_id=None):
    """在 Google Drive 建立資料夾，若已存在則直接回傳 ID"""
    try:
        # 先檢查是否已經存在同名資料夾
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
            
        # 加上 supportsAllDrives 解決 Service Account Quota 問題
        results = service.files().list(
            q=query, 
            spaces='drive', 
            fields='files(id, name)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        items = results.get('files', [])
        
        if items:
            print(f"資料夾 {folder_name} 已存在 (ID: {items[0]['id']})")
            return items[0]['id']
            
        # 若不存在則建立
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
            
        folder = service.files().create(
            body=file_metadata, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        folder_id = folder.get('id')
        print(f"成功建立資料夾: {folder_name} (ID: {folder_id})")
        return folder_id
    except Exception as e:
        print(f"⚠️ 建立資料夾失敗 ({folder_name}): {e}")
        return None

def upload_file(service, file_path, parent_id):
    """將本地檔案上傳到指定的 Google Drive 資料夾"""
    try:
        file_name = os.path.basename(file_path)
        
        # 簡單預判 mimeType
        mime_type = 'application/octet-stream'
        if file_name.endswith('.csv'):
            mime_type = 'text/csv'
        elif file_name.endswith('.json'):
            mime_type = 'application/json'
        elif file_name.endswith('.png'):
            mime_type = 'image/png'
        elif file_name.endswith('.pdf'):
            mime_type = 'application/pdf'
            
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }
        
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        
        file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id',
            supportsAllDrives=True
        ).execute()
        print(f"  ✅ 成功上傳: {file_name} (ID: {file.get('id')})")
        return file.get('id')
    except Exception as e:
        print(f"  ⚠️ 上傳檔案失敗 ({file_path}): {e}")
        return None

def main():
    service = get_gdrive_service()
    if not service:
        return
        
    print(f"開始執行 Google Drive 雲端備份作業...")
    
    import pytz
    tw_tz = pytz.timezone("Asia/Taipei")
    
    # 建立今日日期資料夾
    today_str = datetime.now(tw_tz).strftime("%Y-%m-%d")
    today_folder_id = create_folder(service, f"Daily_Report_{today_str}", parent_id=TARGET_FOLDER_ID)
    
    if not today_folder_id:
        print("無法建立根目錄，中止上傳。")
        return
        
    # 1. 上傳 daily_reports 裡面的檔案 (如 csv, json, pdf)
    report_dir = "daily_reports"
    if os.path.exists(report_dir):
        print(f"\n📁 準備上傳報表檔 ({report_dir}/)...")
        for filename in os.listdir(report_dir):
            file_path = os.path.join(report_dir, filename)
            if os.path.isfile(file_path) and today_str in filename: # 只上傳今天的報表
                upload_file(service, file_path, today_folder_id)

    # 2. 上傳 screenshots 裡面的圖片
    screenshot_dir = os.path.join("screenshots", today_str)
    if os.path.exists(screenshot_dir):
        print(f"\n📁 準備上傳 K 線圖 ({screenshot_dir}/)...")
        # 建立截圖子資料夾
        kline_folder_id = create_folder(service, "K_Line_Charts", parent_id=today_folder_id)
        if kline_folder_id:
            for filename in os.listdir(screenshot_dir):
                file_path = os.path.join(screenshot_dir, filename)
                if os.path.isfile(file_path):
                    upload_file(service, file_path, kline_folder_id)
                    
    print("\n🎉 Google Drive 備份作業完成！")

if __name__ == "__main__":
    main()
