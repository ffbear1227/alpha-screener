import datetime
import json
import os
import pandas as pd
import requests
import yfinance as yf

# ==========================================
# 1. 你的板塊監控清單 (可隨時在此增減)
# ==========================================
WATCHLIST = {
    "太空概念": ["RKLB", "ASTS", "LUNR", "SPCE", "MAXR", "IRDM", "PL", "GSAT"],
    "AI半導體": ["NVDA", "PLTR", "SMCI", "AMD", "TSLA", "ARM", "AVGO", "MSFT", "GOOGL"],
    "加密貨幣概念": ["MSTR", "COIN", "HOOD"]
}

# 從系統環境變數讀取 Telegram 金鑰 (GitHub Actions 執行時會自動灌入)
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")


def calculate_indicators(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")

        if len(df) < 60:  # 新上市或資料不足剔除
            return None

        # 計算 EMA
        df["EMA5"] = df["Close"].ewm(span=5, adjust=False).mean()
        df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

        # 計算 RVOL (今日成交量 / 過去20日平均成交量)
        df["VOL_20MA"] = df["Volume"].rolling(window=20).mean()
        df["RVOL"] = df["Volume"] / df["VOL_20MA"]

        # 計算 52周最高價 (過去252個交易日)
        df["52W_High"] = df["High"].rolling(window=252, min_periods=100).max()

        current = df.iloc[-1]
        info = stock.info
        market_cap = info.get("marketCap", 0)

        return {
            "close": current["Close"],
            "high": current["High"],
            "ema5": current["EMA5"],
            "ema10": current["EMA10"],
            "ema20": current["EMA20"],
            "ema50": current["EMA50"],
            "rvol": current["RVOL"],
            "high_52w": current["52W_High"],
            "market_cap": market_cap,
            "next_earnings": info.get("earningsTimestamp", None)
        }
    except Exception:
        # 單一標的遇到下市或抓取錯誤時，靜默跳過，不干擾其他股票
        return None


def run_screener():
    # 條件 0: 大盤 SPY 是否 > 20EMA？
    spy = calculate_indicators("SPY")
    
    if not spy:
        print("⚠️ 提醒：無法取得 SPY 報價（可能為非交易時段或網路延遲），系統放行繼續篩選...")
    else:
        if spy["close"] <= spy["ema20"]:
            print(f"📉 大盤 SPY 現價 (${round(spy['close'], 2)}) 低於 20EMA (${round(spy['ema20'], 2)})，系統按紀律暫停做多篩選。")
            return []
        else:
            print(f"📈 大盤趨勢健康：SPY (${round(spy['close'], 2)}) > 20EMA (${round(spy['ema20'], 2)})")

    passed_stocks = []
    flat_list = [(sector, sym) for sector, syms in WATCHLIST.items() for sym in syms]

    for sector, sym in flat_list:
        data = calculate_indicators(sym)
        if not data:
            continue

        # 邏輯 A：市值 > 1億美金
        if data["market_cap"] < 100_000_000:
            continue

        # 邏輯 B：多頭排列 (5EMA > 10EMA > 20EMA > 50EMA)
        if not (data["ema5"] > data["ema10"] and data["ema10"] > data["ema20"] and data["ema20"] > data["ema50"]):
            continue

        # 邏輯 C：股價 > 5EMA
        if data["close"] <= data["ema5"]:
            continue

        # 邏輯 D：股價突破或極度貼近 52周最高 (給予0.5%緩衝判定突破)
        if data["high"] < (data["high_52w"] * 0.995):
            continue

        # 邏輯 E：RVOL > 1.5
        # 【本地強行測試開關】：如果你現在想強行收到推播看效果，把下一行改成 if data["rvol"] <= 0.0:
        if data["rvol"] <= 1.5:
            continue

        # 邏輯 F：距離財報日 3 日以上
        if data["next_earnings"]:
            earnings_date = datetime.datetime.fromtimestamp(data["next_earnings"])
            days_to_earnings = (earnings_date - datetime.datetime.now()).days
            if 0 <= days_to_earnings <= 3:
                continue

        passed_stocks.append({
            "symbol": sym,
            "sector": sector,
            "price": round(data["close"], 2),
            "rvol": round(data["rvol"], 2),
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        })

    return passed_stocks


def send_telegram(stocks):
    if not stocks or not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️ 未偵測到 Telegram Token 或 Chat ID，跳過推播發送。")
        return

    # 改用 HTML 解析，最不容易因為股票價格的小數點崩潰
    msg = "🚀 <b>美股領頭羊動能突破通知</b> 🚀\n\n"
    for s in stocks:
        msg += f"• <b>{s['symbol']}</b> ({s['sector']})\n"
        msg += f"  股價: <code>${s['price']}</code> | RVOL: <b>{s['rvol']}x</b>\n\n"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    res = requests.post(url, json={
        "chat_id": TG_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    })

    if res.status_code == 200:
        print("✅ Telegram 通知發送成功！")
    else:
        print(f"❌ Telegram 發送失敗，錯誤碼：{res.text}")


if __name__ == "__main__":
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 系統啟動，開始執行個股運算...")
    results = run_screener()
    print(f"篩選結束，本時段共計 {len(results)} 檔標的符合突破條件。")

    # 寫入 results.json (指定 utf-8 確保中文板塊名稱正常顯示)
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump({
            "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(results),
            "data": results
        }, f, ensure_ascii=False, indent=2)

    if len(results) > 0:
        send_telegram(results)
