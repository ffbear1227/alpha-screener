import datetime
import json
import os
import pandas as pd
import requests
import yfinance as yf

# ==========================================
# 終極量化版：美股 14 大板塊「雙引擎與廣度政變軍火庫」
# ==========================================
THEMES = {
    "半導體與設備": {
        "parent": "SMH",
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
        "parent": "IGV",
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
        "parent": "CIBR",
        "children": ["CRWD", "PANW", "FTNT", "ZS", "CYBR", "OKTA", "SNTL"],
    },
    "AI電網與散熱基建": {
        "parent": "PAVE",
        "children": ["VRT", "ETN", "PWR", "GE", "PH", "NVT", "FIX", "EMR"],
    },
    "太空與國防": {
        "parent": "ITA",
        "children": ["RKLB", "ASTS", "LUNR", "LMT", "RTX", "GD", "TDY", "HEI"],
    },
    "加密貨幣與礦企": {
        "parent": "IBIT",
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
        "parent": "NLR",
        "children": ["VST", "CEG", "TLN", "BWXT", "CCJ", "OKLO", "SMR", "LEU"],
    },
    "高動能電動車": {
        "parent": "IDRV",
        "children": ["TSLA", "RIVN", "LCID", "XPEV", "LI", "ON"],
    },
    "美股七雄 (Mag7)": {
        "parent": "QQQ",
        "children": ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"],
    },
    "前沿生技與減重": {
        "parent": "XBI",
        "children": ["LLY", "NVO", "VKTX", "VRTX", "REGN", "CRSP", "ALNY"],
    },
    "數位金融與支付": {
        "parent": "FINX",
        "children": ["SQ", "SOFI", "AFRM", "PYPL", "NU", "TOST", "FLYW"],
    },
    "貴金屬與礦業": {
        "parent": "GLD",
        "children": ["NEM", "AEM", "GOLD", "FNV", "PAAS", "AG"],
    },
    "全球數位電商": {
        "parent": "XLY",
        "children": ["AMZN", "SHOP", "MELI", "SE", "CPNG", "DLO"],
    },
    "中概網路龍頭": {
        "parent": "KWEB",
        "children": ["BABA", "PDD", "JD", "BIDU", "NTES", "TCOM", "BEKE"],
    },
}

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")


def calculate_indicators(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")

        if len(df) < 60:
            return None

        # 計算 EMA
        df["EMA5"] = df["Close"].ewm(span=5, adjust=False).mean()
        df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

        # 計算 RVOL
        df["VOL_20MA"] = df["Volume"].rolling(window=20).mean()
        df["RVOL"] = df["Volume"] / df["VOL_20MA"]

        # 計算 52周最高 與 20日最高 (解決滯後性關鍵)
        df["52W_High"] = df["High"].rolling(window=252, min_periods=100).max()
        df["20D_High"] = df["High"].rolling(window=20, min_periods=10).max()

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
            "high_20d": current["20D_High"],
            "market_cap": info.get("marketCap", 0),
            "next_earnings": info.get("earningsTimestamp", None),
        }
    except Exception:
        return None


def run_screener():
    # 【第 0 層大盤總閘門】
    spy = calculate_indicators("SPY")
    if not spy or spy["close"] <= spy["ema20"]:
        print("大盤 SPY 跌破 20EMA，系統總閘門關閉。")
        return [], []

    passed_stocks = []
    blocked_sectors = []

    for theme_name, data in THEMES.items():
        parent_sym = data["parent"]
        children = data["children"]

        # 1. 取得門神狀態
        p_data = calculate_indicators(parent_sym)
        proxy_is_up = p_data and (p_data["close"] > p_data["ema20"])

        # 2. 預先抓取所有子弟兵的數據（用來算廣度，同時避免稍後重複 Call API）
        children_dict = {}
        healthy_count = 0

        for sym in children:
            c_data = calculate_indicators(sym)
            if not c_data:
                continue
            children_dict[sym] = c_data
            if c_data["close"] > c_data["ema20"]:
                healthy_count += 1

        total_valid = len(children_dict)
        if total_valid == 0:
            continue

        # 3. 計算板塊內部廣度 (站上20EMA的比例)
        breadth_ratio = healthy_count / total_valid

        # ★ 廣度政變判定：門神雖倒，但若板塊內 >= 50% 存活，強制開門！
        gate_status = "BLOCKED"
        gate_desc = ""

        if proxy_is_up:
            gate_status = "OPEN"
            gate_desc = "ETF門神"
        elif breadth_ratio >= 0.5:
            gate_status = "OPEN"
            gate_desc = f"廣度起義({round(breadth_ratio*100)}%)"

        if gate_status == "BLOCKED":
            blocked_sectors.append(f"{theme_name}({parent_sym})")
            continue

        # 4. 掃描房間內的個股
        for sym, s in children_dict.items():
            if s["market_cap"] < 100_000_000:
                continue

            if s["next_earnings"]:
                earnings_date = datetime.datetime.fromtimestamp(
                    s["next_earnings"]
                )
                days_to_earnings = (
                    earnings_date - datetime.datetime.now()
                ).days
                if 0 <= days_to_earnings <= 3:
                    continue

            # ==========================================
            # ★ 雙引擎動能突破判定 (滿足 A 或 B 皆可)
            # ==========================================

            # 【引擎 A】：經典 52 周強勢領頭羊
            engine_a = (
                (s["ema5"] > s["ema10"] > s["ema20"] > s["ema50"])
                and (s["close"] > s["ema5"])
                and (s["high"] >= s["high_52w"] * 0.995)
                and (s["rvol"] > 1.5)
            )

            # 【引擎 B】：口袋支點 / 底部起漲引擎 (克服滯後性)
            engine_b = (
                (s["close"] > s["ema20"])
                and (s["close"] > s["ema50"])
                and (s["ema5"] > s["ema10"] > s["ema20"])
                and (s["close"] > s["ema5"])
                and (s["high"] >= s["high_20d"] * 0.995)
                and (s["rvol"] > 2.0)  # 底部發動，爆量要求更嚴格
            )

            if engine_a or engine_b:
                signal_type = "🚀 52W創高" if engine_a else "⚡ 底部發動"

                passed_stocks.append(
                    {
                        "symbol": sym,
                        "sector": theme_name,
                        "proxy": parent_sym,
                        "price": round(s["close"], 2),
                        "rvol": round(s["rvol"], 2),
                        "signal": signal_type,
                        "gate": gate_desc,
                    }
                )

    return passed_stocks, blocked_sectors


def send_telegram(stocks, blocked):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return

    msg = "🔥 **Alpha 實時動能掃描** 🔥\n\n"

    if stocks:
        for s in stocks:
            msg += f"• **{s['symbol']}** `[{s['sector']}]`\n"
            msg += f"  🏷️ **{s['signal']}** `({s['gate']})`\n"
            msg += f"  現價: ${s['price']} | 爆量: {s['rvol']}x\n\n"
    else:
        msg += "本次時段無標的觸發雙引擎雷達。\n\n"

    if blocked:
        msg += "─── 🛡️ 門神與廣度雙重封鎖板塊 ───\n"
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