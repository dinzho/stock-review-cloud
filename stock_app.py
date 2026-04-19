import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import json

st.set_page_config(page_title="港A股覆盤平台", page_icon="📊", layout="wide")
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "daily_data"

@st.cache_data(ttl=3600)
def load_review_data():
    if not DATA_DIR.exists(): return {}
    files = sorted(DATA_DIR.glob("*.json"), reverse=True)
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in files}

def show_review():
    st.title("📅 每日港A收市覆盤")
    data_map = load_review_data()
    if not data_map:
        st.info("📂 暫無數據。等待每日雲端自動抓取或手動觸發工作流。")
        return
    selected = st.selectbox("📆 選擇日期", list(data_map.keys()))
    data = data_map[selected]
    cols = st.columns(3)
    for i, (name, val) in enumerate(data["indices"].items()):
        cols[i].metric(name, val.get("close"), f"{val.get('pct',0):+.2f}%")
    st.info(f"💰 南向: `{data['funds'].get('南向','N/A')}` | 北向: `{data['funds'].get('北向','N/A')}`")
    if data["sectors"]["top"]: st.dataframe(pd.DataFrame(data["sectors"]["top"]), hide_index=True)
    st.success(f"📈 趨勢：`{data['tech']['trend']}`")

# === 簡化版個股查詢（保持輕量） ===
def show_stock():
    st.title("🔍 個股快速分析")
    ticker = st.text_input("股票代碼 (例: 0700.HK / AAPL / 600519.SS)", "0700.HK").upper()
    if st.button("查詢"):
        try:
            df = yf.Ticker(ticker).history(period="1y")
            if df.empty: st.error("無數據"); return
            cp, pp = df['Close'].iloc[-1], df['Close'].iloc[-2]
            pct = ((cp-pp)/pp)*100
            st.metric(ticker, f"{cp:.2f}", f"{pct:+.2f}%")
            st.line_chart(df['Close'])
        except Exception as e: st.error(f"查詢失敗: {e}")

tab1, tab2 = st.tabs(["📅 每日覆盤", "🔍 個股查詢"])
with tab1: show_review()
with tab2: show_stock()