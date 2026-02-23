import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# 設定我們需要什麼權限 (上傳到 Drive)
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    creds = None
    # 如果已經生成過授權，直接讀取
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # 如果還沒有授權，或是過期了，就重新跑授權流程
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("\n❌ 找不到 credentials.json 檔案！")
                print("請依照指示，前往 Google Cloud Console 下載「OAuth 2.0 用戶端 ID」的 JSON 檔")
                print("並將其重新命名為 'credentials.json' 放在這個資料夾下。")
                return
                
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # 儲存最新的 token
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # 輸出成 Base64 字串，方便複製到 GitHub Secrets
    with open('token.json', 'r') as token_file:
        token_str = token_file.read()
        b64_str = base64.b64encode(token_str.encode('utf-8')).decode('utf-8')
        
        print("\n" + "="*70)
        print("🎉 網頁授權成功！這代表 Google Drive 知道你是誰了。")
        print("👇 請複製下方這「整串亂碼」，並覆蓋掉 GitHub 中的 GCP_CREDENTIALS_B64 Secret：")
        print("="*70 + "\n")
        
        print(b64_str)
        
        print("\n" + "="*70)

if __name__ == '__main__':
    main()
