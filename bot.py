import os
import discord
from discord.ext import commands
import json
import requests

import matplotlib.pyplot as plt
import pandas as pd
from io import BytesIO

# =========================
# TOKENS
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

if not TOKEN:
    print("MISSING DISCORD TOKEN")
    exit()

if not ALPACA_KEY or not ALPACA_SECRET:
    print("MISSING ALPACA KEYS")

BASE_URL = "https://data.alpaca.markets/v2"

headers = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET
}

# =========================
# MEMORY
# =========================
FILE = "memory.json"

def load():
    try:
        return json.load(open(FILE))
    except:
        return {}

def save(d):
    json.dump(d, open(FILE, "w"), indent=4)

memory = load()

def user(uid):
    if uid not in memory:
        memory[uid] = {
            "watchlist": [],
            "mode": "swing",
            "risk": "C",
            "agent": None
        }
    return memory[uid]

# =========================
# FIXED ALPACA DATA FETCH
# =========================
def get_data(symbol, timeframe="1Min"):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": timeframe,
            "limit": 50,
            "feed": "iex"   # CRITICAL FIX
        }

        r = requests.get(url, headers=headers, params=params)

        data = r.json()

        print("ALPACA RAW:", data)  # DEBUG

        bars = data.get("bars")

        if not bars:
            print("NO BARS RETURNED FOR:", symbol)
            return None

        close = [b["c"] for b in bars]
        high = [b["h"] for b in bars]
        vol = [b["v"] for b in bars]

        return close, high, vol

    except Exception as e:
        print("DATA ERROR:", e)
        return None

# =========================
# ANALYSIS ENGINE
# =========================
def analyze(symbol, mode="swing"):
    data = get_data(symbol, "1Min")

    if not data:
        return None

    close, high, vol = data

    price = close[-1]

    resistance = max(close[-20:])
    support = min(close[-20:])

    breakout = price > resistance
    rejection = high[-1] >= resistance and close[-1] < resistance

    retest = False
    if len(close) > 10:
        broke = max(close[-10:]) > resistance
        retest = broke and abs(price - resistance) / resistance < 0.005

    vol_spike = vol[-1] > (sum(vol[-20:]) / 20) * 1.8 if len(vol) > 20 else False

    change = ((close[-1] - close[-5]) / close[-5]) * 100 if len(close) > 5 else 0

    score = 0

    if mode == "scalp":
        bw, rw, rj = 50, 40, -50
    elif mode == "daytrade":
        bw, rw, rj = 60, 50, -40
    elif mode == "smc":
        bw, rw, rj = 30, 60, -35
    else:
        bw, rw, rj = 60, 50, -30

    if breakout:
        score += bw
    if retest:
        score += rw
    if rejection:
        score += rj
    if vol_spike:
        score += 30
    if change > 0.5:
        score += 15

    if score >= 80:
        label = "🚀 STRONG BREAKOUT"
    elif score >= 55:
        label = "🔥 GOOD SETUP"
    elif score >= 30:
        label = "👀 WATCH"
    else:
        label = "❌ WEAK"

    return {
        "symbol": symbol,
        "price": price,
        "resistance": resistance,
        "support": support,
        "breakout": breakout,
        "retest": retest,
        "rejection": rejection,
        "volume_spike": vol_spike,
        "score": score,
        "label": label
    }

# =========================
# SAFE CHARTS
# =========================
def make_chart(symbol, timeframe="1Min"):
    data = get_data(symbol, timeframe)

    if not data:
        return None

    close, high, vol = data

    plt.figure(figsize=(10,4))
    plt.plot(close, label="Price")

    plt.axhline(max(close), color="red", linestyle="--", label="Resistance")
    plt.axhline(min(close), color="green", linestyle="--", label="Support")

    plt.title(f"{symbol} {timeframe}")
    plt.legend()

    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()

    return buf

# =========================
# BOT
# =========================
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synced")

bot = Bot()

# =========================
# COMMANDS
# =========================

@bot.tree.command(name="rate")
async def rate(i: discord.Interaction, ticker: str):
    u = user(str(i.user.id))

    d = analyze(ticker.upper(), u["mode"])
    if not d:
        await i.response.send_message("❌ No data (Alpaca issue / market closed)")
        return

    await i.response.send_message(
        f"📊 {ticker}\n{d['label']}\n"
        f"Price: {d['price']}\n"
        f"Score: {d['score']}"
    )

@bot.tree.command(name="scan")
async def scan(i: discord.Interaction):
    await i.response.defer()

    u = user(str(i.user.id))
    tickers = ["AAPL","TSLA","NVDA","MSFT","AMZN"]

    out = []

    for t in tickers:
        d = analyze(t, u["mode"])
        if d:
            out.append(f"{t}: {d['label']} ({d['score']})")

    if not out:
        await i.followup.send("❌ No market data available (likely Alpaca feed/market issue)")
        return

    await i.followup.send("\n".join(out))

@bot.tree.command(name="chart")
async def chart(i: discord.Interaction, ticker: str, timeframe: str = "1Min"):
    await i.response.defer()

    img = make_chart(ticker.upper(), timeframe)

    if not img:
        await i.followup.send("❌ No chart data available")
        return

    file = discord.File(img, filename="chart.png")

    await i.followup.send(file=file)

@bot.tree.command(name="modes")
async def modes(i: discord.Interaction):
    await i.response.send_message(
        "swing | daytrade | scalp | smc | investor"
    )

@bot.tree.command(name="help")
async def help(i: discord.Interaction):
    await i.response.send_message(
        "/rate\n/scan\n/chart\n/modes\n"
    )

# =========================
# RUN
# =========================
bot.run(TOKEN)
