# daily_review.py - 🇭🇰 港股每日覆盤 (含VIX/港股板塊/動態明日關注)
import yfinance as yf
import pandas as pd
import requests
import json
import datetime
import time
import sys
from pathlib import Path

# 🔑 飛書 Webhook
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/67f931b1-581d-40c2-ad3b-a0f5c19076f0"
DATA_DIR = Path("daily_data")
DATA_DIR.mkdir(exist_ok=True)

# 🔄 重試裝飾器
def retry(max_attempts=3, delay=2):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    print(f"⚠️ 第{attempt+1}次失敗，{delay}秒後重試...")
                    time.sleep(delay)
        return wrapper
    return decorator

def is_trading_day():
    """簡化判斷：週一至週五"""
    return datetime.datetime.now().date().weekday() < 5

def calculate_fib_levels(high, low, current):
    """計算斐波那契回撤/擴展關鍵位"""
    rng = high - low
    fib_ret = {
        "0.236": round(high - rng * 0.236, 2), "0.382": round(high - rng * 0.382, 2),
        "0.500": round(high - rng * 0.500, 2), "0.618": round(high - rng * 0.618, 2),
        "0.786": round(high - rng * 0.786, 2)
    }
    fib_ext = {
        "1.272": round(high + rng * 0.272, 2), "1.618": round(high + rng * 0.618, 2),
        "2.000": round(high + rng * 1.000, 2), "2.618": round(high + rng * 1.618, 2)
    }
    if current > high: pos = "📈 突破前高，看向擴展位"
    elif current < low: pos = "📉 跌破前低，注意風險"
    elif current > fib_ret["0.500"]: pos = "⚖️ 位於中軸上方，偏多結構"
    else: pos = "⚖️ 位於中軸下方，偏空結構"
    return {"retracements": fib_ret, "extensions": fib_ext, "position": pos, "range": f"{low:.2f} ~ {high:.2f}"}

@retry(max_attempts=3, delay=2)
def fetch_index_with_fib(ticker, name, period="20d"):
    """抓取指數 + FIB"""
    df = yf.Ticker(ticker).history(period=period)
    if len(df) < 5: return None
    cur, prev = df['Close'].iloc[-1], df['Close'].iloc[-2]
    pct = (cur - prev) / prev * 100
    high, low = df['High'].iloc[-20:].max(), df['Low'].iloc[-20:].min()
    return {"close": round(cur, 2), "pct": round(pct, 2), "fib": calculate_fib_levels(high, low, cur)}

@retry(max_attempts=3, delay=2)
def fetch_vix_sentiment():
    """抓取 VIX & 情緒"""
    df = yf.Ticker("^VIX").history(period="1d")
    if df.empty: return {"value": "N/A", "sentiment": "數據不足"}
    v = round(df['Close'].iloc[-1], 2)
    s = "😎 樂觀/貪婪" if v < 15 else ("😐 平穩/中性" if v < 20 else ("😰 恐慌/謹慎" if v < 30 else "🚨 極度恐慌"))
    return {"value": v, "sentiment": s}

@retry(max_attempts=3, delay=2)
def fetch_hk_sectors():
    """港股熱門板塊（用代表性個股模擬）"""

    # 科技/金融/地產/消費/電信/能源 代表性港股
    stocks = {
        "科技": "0700.HK", "金融": "0005.HK", "地產": "1109.HK",
        "消費": "0291.HK", "電信": "0941.HK", "能源": "0883.HK"
    }
    results = []
    for name, code in stocks.items():
        try:
            df = yf.Ticker(code).history(period="2d")
            if len(df) >= 2:
                pct = (df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
                results.append({"name": name, "pct": round(pct, 2)})
        except: pass
    results.sort(key=lambda x: x["pct"], reverse=True)
    return results[:3]

def fetch_market_data():
    """主抓取函數"""
    print("🔍 抓取恆指 + FIB...")
    hsi = fetch_index_with_fib("^HSI", "恆指")
    
    print("🔍 抓取A股（備援）...")
    sh = fetch_index_with_fib("000001.SS", "上證")
    
    print("🔍 抓取 VIX & 情緒...")
    vix = fetch_vix_sentiment()
    
    print("🔍 抓取港股熱門板塊...")
    sectors = fetch_hk_sectors()
    
    # 趨勢判斷（優先恆指）
    ref = hsi or sh
    trend = "數據不足"
    if ref:
        p = ref["pct"]
        trend = "多頭偏強" if p > 0.5 else ("空頭承壓" if p < -0.5 else "震盪整理")
    
    return {
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "hsi": hsi, "sh": sh, "vix": vix, "sectors": sectors,
        "trend": trend
    }

def format_feishu_md(data):
    """格式化飛書 Markdown"""
    d = data["date"]
    hsi = data["hsi"] or {"close": "N/A", "pct": 0, "fib": None}
    sh = data["sh"] or {"close": "N/A", "pct": 0}
    vix = data["vix"]
    sectors = data["sectors"]
    trend = data["trend"]
    
    # 大盤表格
    hk_row = f"| 恆生指數 | `{hsi['close']}` | `{hsi['pct']:+.2f}%` |"
    cn_row = f"| 上證指數 | `{sh['close']}` | `{sh['pct']:+.2f}%` |" if sh["close"] != "N/A" else ""
    tbl = f"{cn_row}\n{hk_row}".strip()
    
    # 板塊
    sec_md = "\n".join([f"{i+1}. **{x['name']}** (`{x['pct']:+.2f}%`)" for i, x in enumerate(sectors)]) if sectors else "• 板塊輪動快，無明顯主線"
    
    # FIB
    fib = hsi.get("fib")
    fib_md = "• 計算中...\n"
    if fib:
        r, e = fib["retracements"], fib["extensions"]
        fib_md = f"""**📐 斐波那契回撤 (關鍵支撐/阻力)**
| 比例 | 價格 | 說明 |
|------|------|------|
| 0.382 | `{r['0.382']:.2f}` | 次級支撐/阻力 |
| 0.500 | `{r['0.500']:.2f}` | ⚖️ 黃金中軸 (多空分水嶺) |
| 0.618 | `{r['0.618']:.2f}` | ✨ 黃金分割關鍵位 |

**🎯 擴展位 (目標價)**
| 比例 | 價格 | 說明 |
|------|------|------|
| 1.272 | `{e['1.272']:.2f}` | 初級目標 |
| 1.618 | `{e['1.618']:.2f}` | ✨ 黃金擴展 |

📍 區間：`{fib['range']}` | 
📊 位置：{fib['position']}"""
    
    # 🔥 動態明日關注（根據趨勢 + VIX 自動生成）
    focus = []
    try:
        v_num = float(str(vix["value"]).replace("N/A", "20"))
        if v_num > 25: focus.append("• VIX 高企，注意避險資產與波動率對沖")
        elif v_num < 15: focus.append("• VIX 低位，留意風險資產過度樂觀信號")
    except: pass
    
    if trend == "多頭偏強":
        focus.append("• 趨勢偏多，留意前高突破確認與量能配合")
    elif trend == "空頭承壓":
        focus.append("• 趨勢偏空，關注關鍵支撐位防守與反彈賣壓")
    else:
        focus.append("• 震盪格局，高拋低吸為主，避免追漲殺跌")
    
    focus.append("• 關注南向資金流向與政策面動態")
    focus_md = "\n".join(focus)
    
    return f"""📅 **{d} 🇭🇰 港股每日覆盤**

📊 **大盤表現**
| 市場 | 收盤 | 漲跌幅 |
|------|------|--------|
{tbl}

🌪️ **VIX 恐慌指數 & 全球情緒**
數值：`{vix['value']}` | 情緒：`{vix['sentiment']}`

🔥 **港股熱門板塊（代表性個股）**
{sec_md}


📈 **技術信號 & FIB 黃金分割分析**
趨勢：`{trend}`

{fib_md}

🔔 **明日關注**
{focus_md}

⚠️ 數據僅供參考，不構成投資建議"""

def send_to_feishu(webhook, md_text):
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "📊 港股每日覆盤"}},
            "elements": [{"tag": "markdown", "content": md_text}]
        }
    }
    try:
        resp = requests.post(webhook, json=payload, timeout=20)
        if resp.status_code == 200 and resp.json().get("code") == 0:
            print("✅ 飛書推送成功"); return True
        print(f"❌ 推送失敗: {resp.text}"); return False
    except Exception as e:
        print(f"❌ 請求錯誤: {e}"); return False

def run_daily_job():
    print(f"\n🔍 [{datetime.datetime.now().strftime('%H:%M:%S')}] 開始執行...")
    if not is_trading_day():
        print("📅 非交易日，跳過執行。"); return
    
    data = fetch_market_data()
    file_path = DATA_DIR / f"{data['date']}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 數據已存檔: {file_path}")
    
    md_text = format_feishu_md(data)
    print("\n📝 預覽內容：\n" + "="*50 + "\n" + md_text + "\n" + "="*50)
    send_to_feishu(FEISHU_WEBHOOK, md_text)
    print("✨ 任務完成\n")

def start_1700_scheduler():
    print("⏰ 定時任務已啟動，等待每日 17:00 執行...")
    last_run_date = None
    while True:
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        if now.hour == 17 and now.minute == 0 and now.second < 60 and last_run_date != today_str:
            run_daily_job()
            last_run_date = today_str
        time.sleep(30)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("🧪 測試模式：立即執行一次")
        run_daily_job()
    else:
        start_1700_scheduler()
