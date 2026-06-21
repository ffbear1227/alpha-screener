import datetime
import json
import os
import pandas as pd
import requests
import yfinance as yf

# ==========================================
# 終極版：美股全領域「母子映射門神軍火庫」
# 總計 14 大板塊，涵蓋 102 檔高動能領頭羊
# ==========================================
THEMES = {
    # ─── 【第一梯隊：核心科技與AI基建】 ───
    "半導體與設備": {
        "parent": "SMH",  # 門神：VanEck半導體ETF
        "children": [
            "NVDA",
            "TSM",
            "AVGO",
            "AMD",
            "QCOM",
            "ARM",
            "MU",
            "ASML",
            "KLAC",
            "AMAT",
        ],
    },
    "雲端與大數據": {
        "parent": "IGV",  # 門神：北美軟體服務ETF
        "children": [
            "PLTR",
            "NOW",
            "CRM",
            "SNOW",
            "DDOG",
            "MDB",
            "NET",
            "ADBE",
        ],
    },
    "網路安全 (Sec)": {
        "parent": "CIBR",  # 門神：第一信託資安ETF
        "children": ["CRWD", "PANW", "FTNT", "ZS", "CYBR", "OKTA", "SNTL"],
    },
    "AI電網與散熱基建": {
        "parent": "PAVE",  # 門神：美國基礎建設ETF
        "children": ["VRT", "ETN", "PWR", "GE", "PH", "NVT", "FIX", "EMR"],
    },
    # ─── 【第二梯隊：前沿破壞性創新】 ───
    "太空與國防": {
        "parent": "ITA",  # 門神：美國航太與國防ETF
        "children": ["RKLB", "ASTS", "LUNR", "LMT", "RTX", "GD", "TDY", "HEI"],
    },
    "加密貨幣與礦企": {
        "parent": "IBIT",  # 門神：貝萊德比特幣現貨ETF
        "children": [
            "MSTR",
            "COIN",
            "HOOD",
            "MARA",
            "CLSK",
            "IREN",
            "HUT",
            "CIFR",
        ],
    },
    "核能與次世代電力": {
        "parent": "NLR",  # 純度升級：VanEck鈾與核能ETF
        "children": ["VST", "CEG", "TLN", "BWXT", "CCJ", "OKLO", "SMR", "LEU"],
    },
    "高動能電動車": {
        "parent": "IDRV",  # 門神：iShares自駕與EV ETF
        "children": ["TSLA", "RIVN", "LCID", "XPEV", "LI", "ON"],
    },
    # ─── 【第三梯隊：巨頭、生技與新金融】 ───
    "美股七雄 (Mag7)": {
        "parent": "QQQ",  # 門神：納斯達克100
        "children": ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"],
    },
    "前沿生技與減重": {
        "parent": "XBI",  # 門神：SPDR生技ETF
        "children": ["LLY", "NVO", "VKTX", "VRTX", "REGN", "CRSP", "ALNY"],
    },
    "數位金融與支付": {
        "parent": "FINX",  # 門神：Global X 金融科技ETF
        "children": ["SQ", "SOFI", "AFRM", "PYPL", "NU", "TOST", "FLYW"],
    },
    # ─── 【第四梯隊：宏觀對沖與全球復甦】 ───
    "貴金屬與礦業": {
        "parent": "GLD",  # 門神：黃金現貨ETF
        "children": ["NEM", "AEM", "GOLD", "FNV", "PAAS", "AG"],
    },
    "全球數位電商": {
        "parent": "XLY",  # 門神：可選消費ETF
        "children": ["AMZN", "SHOP", "MELI", "SE", "CPNG", "DLO"],
    },
    #"中概網路龍頭": {
        "parent": "KWEB",  # 門神：中概網路指數ETF
        "children": ["BABA", "PDD", "JD", "BIDU", "NTES", "TCOM", "BEKE"],
    },
}

# 讀取 GitHub Secrets 環境變數
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")


def calculate_indicators(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")

        if len(df) < 60:
            return None

        # 計算均線
        df["EMA5"] = df["Close"].ewm(span=5, adjust=False).mean()
        df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

        # 計算 RVOL 與 52周最高
        df["VOL_20MA"] = df["Volume"].rolling(window=20).mean()
        df["RVOL"] = df["Volume"] / df["VOL_20MA"]
        df["52W_High"] = df["High"].rolling(window=252, min_periods=100).max()

        current = df.iloc[-1]
        info = stock.info

        return {
            "close": current["Close"],
            "high": current["High"],
            "ema5": current["EMA5"],
            "ema10": current["EMA10"],
            "ema20": current["EMA20"],
            "ema50": current["EMA50"],
            "rvol": current["RVOL"],
            "high_52w": current["52W_High"],
            "market_cap": info.get("marketCap", 0),
            "next_earnings": info.get("earningsTimestamp", None),
        }
    except Exception:
        return None


def run_screener():
    # 【第 0 層大盤總閘門】：SPY 是否站穩 20EMA？
    spy = calculate_indicators("SPY")
    if not spy or spy["close"] <= spy["ema20"]:
        print("大盤 SPY 跌破 20EMA，系統總閘門關閉，暫停做多篩選。")
        return [], []

    passed_stocks = []
    blocked_sectors = []

    for theme_name, data in THEMES.items():
        parent_sym = data["parent"]
        children = data["children"]

        # 【第 1 層門神判定】：該板塊的 ETF Proxy 是否站在 20EMA 之上？
        p_data = calculate_indicators(parent_sym)

        if not p_data or p_data["close"] <= p_data["ema20"]:
            print(
                f"🛑 門神攔截：【{theme_name}】代理 ({parent_sym}) 趨勢轉弱，全組剔除。"
            )
            blocked_sectors.append(f"{theme_name}({parent_sym})")
            continue  # 直接略過該主題底下所有個股！

        print(
            f"🟢 門神放行：【{theme_name}】代理 ({parent_sym}) 趨勢健康，開始掃描個股..."
        )

        # 【第 2 層房間掃描】：門神放行，檢查底下子弟兵
        for sym in children:
            s = calculate_indicators(sym)
            if not s:
                continue

            # 嚴格動能突破濾網
            if s["market_cap"] < 100_000_000:
                continue
            if not (s["ema5"] > s["ema10"] > s["ema20"] > s["ema50"]):
                continue
            if s["close"] <= s["ema5"]:
                continue
            if s["high"] < (s["high_52w"] * 0.995):
                continue
            if s["rvol"] <= 1.5:
                continue

            # 財報日3天內避開
            if s["next_earnings"]:
                earnings_date = datetime.datetime.fromtimestamp(
                    s["next_earnings"]
                )
                days_to_earnings = (
                    earnings_date - datetime.datetime.now()
                ).days
                if 0 <= days_to_earnings <= 3:
                    continue

            passed_stocks.append(
                {
                    "symbol": sym,
                    "sector": theme_name,
                    "proxy": parent_sym,
                    "price": round(s["close"], 2),
                    "rvol": round(s["rvol"], 2),
                }
            )

    return passed_stocks, blocked_sectors


def send_telegram(stocks, blocked):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return

    msg = "🚀 **Alpha 盤中突破通報** 🚀\n\n"

    if stocks:
        for s in stocks:
            msg += f"• **{s['symbol']}** `[{s['sector']}]`\n"
            msg += f"  股價: ${s['price']} | 爆量: {s['rvol']}x | 門神: {s['proxy']}\n\n"
    else:
        msg += "本次時段掃描無符合標準之個股。\n\n"

    if blocked:
        msg += "─── 🛡️ 本期遭門神封鎖板塊 ───\n"
        msg += "、".join(blocked)

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        json={
            "chat_id": TG_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
        },
    )


if __name__ == "__main__":
    results, blocked = run_screener()

    # 寫入 results.json (加入 encoding="utf-8" 防止中文在 Actions 變成亂碼)
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "update_time": datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "count": len(results),
                "blocked_count": len(blocked),
                "blocked_sectors": blocked,
                "data": results,
            },
            f,
            ensure_ascii=False,
        )

    send_telegram(results, blocked)