import os
import json
import datetime
import requests
import akshare as ak
import yfinance as yf
from pathlib import Path

# 🔑 從 GitHub Secrets 讀取 Webhook
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK_URL")
if not FEISHU_WEBHOOK:
    print("⚠️ 未設置 FEISHU_WEBHOOK_URL")
    exit()

# === 🚀 DEBUG 測試代碼（添加這裡）===
print("🚀 [DEBUG] 腳本開始執行")
print(f"🔑 Webhook 長度: {len(FEISHU_WEBHOOK) if FEISHU_WEBHOOK else 0}")
print(f"🔑 Webhook 前 20 字: {FEISHU_WEBHOOK[:20] if FEISHU_WEBHOOK else 'N/A'}")
# === DEBUG 結束 ===

# 統一使用腳本所在目錄作為基準路徑（兼容本地與雲端）
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "daily_data"
DATA_DIR.mkdir(exist_ok=True)

def is_trading_day():
    today = datetime.datetime.now().date()
    if today.weekday() >= 5: return False
    try:
        dates = ak.tool_trade_date_hist_sina()["trade_date"].values
        return today.strftime("%Y-%m-%d") in dates
    except: return True

def fetch_market_data():
    data = {"date": datetime.datetime.now().strftime("%Y-%m-%d"), "indices": {}, "funds": {}, "sectors": {}, "tech": {}}
    try:
        a_idx = ak.stock_zh_index_spot_em()
        sh = a_idx[a_idx['代碼']=='000001'].iloc[0]
        sz = a_idx[a_idx['代碼']=='399001'].iloc[0]
        data["indices"]["上證"] = {"close": float(sh['最新價']), "pct": float(sh['漲跌幅'])}
        data["indices"]["深成"] = {"close": float(sz['最新價']), "pct": float(sz['漲跌幅'])}
    except: data["indices"]["上證"] = {"close": "N/A", "pct": 0}
    
    try:
        hsi = yf.Ticker("^HSI").history(period="1d").tail(1)
        if not hsi.empty:
            data["indices"]["恆指"] = {"close": round(hsi['Close'].iloc[-1], 2), "pct": round(hsi['Close'].pct_change().iloc[-1]*100, 2)}
    except: data["indices"]["恆指"] = {"close": "N/A", "pct": 0}
    
    try:
        north = ak.stock_hsgt_north_net_flow_in_em(symbol="北向資金").tail(1)
        south = ak.stock_hsgt_south_net_flow_in_em(symbol="南向資金").tail(1)
        data["funds"]["北向"] = f"{north['當日資金流入'].iloc[0]/1e4:.1f}億"
        data["funds"]["南向"] = f"{south['當日資金流入'].iloc[0]/1e4:.1f}億"
    except: data["funds"] = {"北向": "N/A", "南向": "N/A"}
    
    try:
        boards = ak.stock_board_industry_name_em()
        data["sectors"]["top"] = boards.nlargest(3, '漲跌幅')[['板塊名稱', '漲跌幅']].to_dict('records')
    except: data["sectors"]["top"] = []
    
    p = data["indices"].get("上證", {}).get("pct", 0)
    data["tech"]["trend"] = "多頭偏強" if p > 0.5 else ("空頭承壓" if p < -0.5 else "震盪整理")
    return data

def format_feishu_md(data):
    d = data["date"]
    sh, sz, hsi = data["indices"].get("上證",{}), data["indices"].get("深成",{}), data["indices"].get("恆指",{})
    north, south = data["funds"].get("北向","N/A"), data["funds"].get("南向","N/A")
    sectors = data["sectors"].get("top",[])
    sec_md = "\n".join([f"{i}. **{s['板塊名稱']}** (`{s['漲跌幅']:.2f}%`)" for i,s in enumerate(sectors,1)]) or "• 輪動較快，無明顯主線"
    
    return f"""📅 **{d} 港A收市覆盤**
📊 **大盤表現**
| 市場 | 收盤 | 漲跌幅 |
|---|---|---|
| 上證指數 | `{sh.get('close','N/A')}` | `{sh.get('pct',0):+.2f}%` |
| 深證成指 | `{sz.get('close','N/A')}` | `{sz.get('pct',0):+.2f}%` |
| 恆生指數 | `{hsi.get('close','N/A')}` | `{hsi.get('pct',0):+.2f}%` |
💰 **資金流向**：南向 `{south}` | 北向 `{north}`
🔥 **熱點板塊**\n{sec_md}
📈 **趨勢**：`{data['tech']['trend']}`
⚠️ *數據僅供參考，不構成投資建議*"""

def send_to_feishu(md_text):
    payload = {"msg_type":"interactive","card":{"header":{"title":{"tag":"plain_text","content":"📊 每日收市覆盤"}},"elements":[{"tag":"markdown","content":md_text}]}}
    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    if resp.status_code == 200 and resp.json().get("code") == 0:
        print("✅ 飛書推送成功")
    else: print(f"❌ 飛書推送失敗: {resp.text}")

if __name__ == "__main__":
    if not is_trading_day():
        print("📅 非交易日，跳過執行。")
        exit()
    print("🔍 正在抓取數據...")
    data = fetch_market_data()
    file_path = DATA_DIR / f"{data['date']}.json"
    with open(file_path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 已存檔: {file_path}")
    send_to_feishu(format_feishu_md(data))
