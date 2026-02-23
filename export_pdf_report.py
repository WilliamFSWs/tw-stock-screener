import os
import glob
import requests
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg

def get_stock_names_mapping():
    print("📡 取得上市股票名稱對照表...")
    try:
        # Disable insecure request warnings for brevity
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        resp = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=30, verify=False)
        resp.raise_for_status()
        return {item.get("公司代號", "").strip(): item.get("公司簡稱", "").strip() for item in resp.json()}
    except Exception as e:
        print(f"⚠️ 無法取得股票名稱對照表: {e}")
        return {}

def create_pdf():
    # 設定字型以支援顯示中文
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'Taipei Sans TC Beta', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False
    
    success_imgs = glob.glob("historical_charts/success/*.png")
    failure_imgs = glob.glob("historical_charts/failure/*.png")
    
    all_imgs = success_imgs + failure_imgs
    if not all_imgs:
        print("❌ 沒有找到任何 K 線圖，請先執行 `python generate_historical_chart.py --bulk N`")
        return
        
    pdf_path = "historical_charts/K線圖勝敗案例對照報告_帶中文名稱.pdf"
    stock_names = get_stock_names_mapping()
    
    print(f"📊 開始產出 PDF 報告，共計 {len(all_imgs)} 張圖表...")
    
    with PdfPages(pdf_path) as pdf:
        for img_path in all_imgs:
            fig, ax = plt.subplots(figsize=(12, 10))
            ax.axis('off')
            
            # 解析檔名來產生中文標註
            basename = os.path.basename(img_path).replace(".png", "")
            parts = basename.split("_")
            
            if len(parts) >= 5:
                status = "✅ 成功案例 (後續長天期發動或突破波段)" if parts[0] == "WIN" else "❌ 失敗案例 (後續未能達標，停損出場)"
                pattern_name = f"{parts[1]}_{parts[2]}" 
                
                stock_code = parts[-3]
                stock_str = f"{stock_code}.TW"
                chinese_name = stock_names.get(stock_code, "")
                if chinese_name:
                    stock_str += f" ({chinese_name})"
                    
                date_str = parts[-1]
                if len(date_str) == 8:
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                
                title = f"{status}\n\n【股票】: {stock_str}   |   【觸發模式】: {pattern_name}   |   【進場訊號日期】: {date_str}"
            else:
                title = f"案例: {basename}"
            
            ax.set_title(title, fontsize=18, fontweight='bold', pad=15)
            
            # 讀取圖片並放入 PDF 中
            img = mpimg.imread(img_path)
            ax.imshow(img)
            
            pdf.savefig(fig, bbox_inches='tight')
            plt.close()
            
    print(f"✅ PDF 報告已經成功產生至: {pdf_path}")

if __name__ == '__main__':
    create_pdf()
