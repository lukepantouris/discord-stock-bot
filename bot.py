import os
import discord
from discord.ext import commands
import json
import requests

import matplotlib.pyplot as plt
import pandas as pd
from io import BytesIO

# =========================
# TOKEN
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("TOKEN NOT FOUND")
    exit()

# =========================
# ALPACA (FREE DATA)
# =========================
ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

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
# MARKET DATA (1M)
# =========================
def get_data(symbol, timeframe="1Min"):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars?timeframe={timeframe}&limit=50"
        r = requests.get(url, headers=headers)
        data = r.json()

        bars = data.get("bars", [])
        if not bars:
            return None

        close = [b["c"] for b in bars]
        high = [b["h"] for b in bars]
        vol = [b["v"] for b in bars]

        return close, high, vol

    except:
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

    broke_before = max(close[-10:]) > resistance
    retest = broke_before and abs(price - resistance) / resistance < 0.005

    vol_spike = vol[-1] > (sum(vol[-20:]) / 20) * 1.8

    change = ((close[-1] - close[-5]) / close[-5]) * 100

    score = 0

    # =========================
    # MODE SYSTEM
    # =========================
    if mode == "scalp":
        breakout_w, retest_w, reject_w = 50, 40, -50
    elif mode == "daytrade":
        breakout_w, retest_w, reject_w = 60, 50, -40
    elif mode == "smc":
        breakout_w, retest_w, reject_w = 30, 60, -35
    elif mode == "investor":
        breakout_w, retest_w, reject_w = 70, 30, -25
    else:
        breakout_w, retest_w, reject_w = 60, 50, -30

    # =========================
    # SIGNALS
    # =========================
    if breakout:
        score += breakout_w
    if retest:
        score += retest_w
    if rejection:
        score += reject_w
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
# CHART SYSTEM (NEW)
# =========================
def make_chart(symbol, timeframe="1Min"):
    data = get_data(symbol, timeframe)

    if not data:
        return None

    close, high, vol = data

    df = pd.DataFrame({"close": close})

    plt.figure(figsize=(10,4))
    plt.plot(df["close"], label="Price")

    resistance = max(close)
    support = min(close)

    plt.axhline(resistance, color="red", linestyle="--", label="Resistance")
    plt.axhline(support, color="green", linestyle="--", label="Support")

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
        await i.response.send_message("❌ No data")
        return

    u["agent"] = ticker.upper()
    save(memory)

    await i.response.send_message(
        f"📊 {ticker}\n"
        f"{d['label']}\n\n"
        f"Price: {d['price']}\n"
        f"Resistance: {d['resistance']}\n"
        f"Support: {d['support']}\n"
        f"Breakout: {d['breakout']}\n"
        f"Retest: {d['retest']}\n"
        f"Rejection: {d['rejection']}\n"
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

    await i.followup.send("\n".join(out))

@bot.tree.command(name="movers")
async def movers(i: discord.Interaction):
    await i.response.defer()

    u = user(str(i.user.id))
    tickers = ["AAPL","TSLA","NVDA","MSFT","AMZN"]

    ranked = []
    for t in tickers:
        d = analyze(t, u["mode"])
        if d:
            ranked.append((t, d["score"]))

    ranked.sort(reverse=True, key=lambda x: x[1])

    msg = "📈 MOVERS\n\n"
    for t, s in ranked:
        msg += f"{t}: {s}\n"

    await i.followup.send(msg)

# =========================
# MODE SYSTEM
# =========================
@bot.tree.command(name="setmode")
async def setmode(i: discord.Interaction, mode: str):
    u = user(str(i.user.id))
    mode = mode.lower()

    if mode not in ["swing","daytrade","scalp","smc","investor"]:
        await i.response.send_message("Invalid mode")
        return

    u["mode"] = mode
    save(memory)

    await i.response.send_message(f"Mode set to {mode}")

@bot.tree.command(name="modes")
async def modes(i: discord.Interaction):
    await i.response.send_message(
        "swing - normal\n"
        "daytrade - intraday\n"
        "scalp - fast moves\n"
        "smc - smart money concepts\n"
        "investor - long term"
    )

# =========================
# CHART COMMAND (NEW)
# =========================
@bot.tree.command(name="chart")
async def chart(i: discord.Interaction, ticker: str, timeframe: str = "1Min"):
    await i.response.defer()

    img = make_chart(ticker.upper(), timeframe)

    if not img:
        await i.followup.send("❌ No data")
        return

    file = discord.File(img, filename="chart.png")

    await i.followup.send(
        content=f"📊 {ticker.upper()} {timeframe}",
        file=file
    )

# =========================
# HELP
# =========================
@bot.tree.command(name="help")
async def help(i: discord.Interaction):
    await i.response.send_message(
        "/rate\n"
        "/scan\n"
        "/movers\n"
        "/chart\n"
        "/setmode\n"
        "/modes\n"
        "/help"
    )

# =========================
# RUN
# =========================
bot.run(TOKEN)
