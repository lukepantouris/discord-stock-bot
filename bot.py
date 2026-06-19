import os

print("ALPACA_KEY =", os.getenv("ALPACA_KEY"))
print("ALPACA_SECRET =", os.getenv("ALPACA_SECRET"))
print("DISCORD_TOKEN =", os.getenv("DISCORD_TOKEN"))
import discord
from discord.ext import commands
import json
import requests
import matplotlib.pyplot as plt
from io import BytesIO

# =========================
# SAFE ENV LOAD (NO CRASH)
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")
ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

if not TOKEN:
    raise Exception("DISCORD_TOKEN missing in Railway")

# 🔥 DO NOT CRASH BOT IF ALPACA MISSING
ALPACA_ENABLED = True
if not ALPACA_KEY or not ALPACA_SECRET:
    print("WARNING: Alpaca keys missing → trading disabled")
    ALPACA_ENABLED = False

BASE_URL = "https://data.alpaca.markets/v2"

headers = {}
if ALPACA_ENABLED:
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }

# =========================
# MEMORY SYSTEM
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
            "mode": "swing",
            "risk": "C"
        }
    return memory[uid]

# =========================
# SAFE ALPACA DATA ENGINE
# =========================
def get_data(symbol, timeframe="1Min"):
    if not ALPACA_ENABLED:
        print("ALPACA DISABLED")
        return None

    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": timeframe,
            "limit": 50,
            "feed": "iex",
            "adjustment": "raw",
            "extended_hours": True
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            print("ALPACA ERROR:", r.status_code, r.text)
            return None

        try:
            data = r.json()
        except:
            print("NON JSON RESPONSE:", r.text)
            return None

        bars = data.get("bars", [])

        # =========================
        # FALLBACK LOGIC
        # =========================
        if not bars:
            print("NO 1MIN DATA → TRY 1DAY")

            params["timeframe"] = "1Day"

            r = requests.get(url, headers=headers, params=params, timeout=10)

            if r.status_code != 200:
                return None

            try:
                data = r.json()
            except:
                return None

            bars = data.get("bars", [])

            if not bars:
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

    retest = abs(price - resistance) / resistance < 0.005 if resistance else False

    vol_spike = False
    if len(vol) > 20:
        vol_spike = vol[-1] > sum(vol[-20:]) / 20 * 1.8

    change = ((close[-1] - close[-5]) / close[-5]) * 100 if len(close) > 5 else 0

    score = 0

    if breakout:
        score += 60
    if retest:
        score += 35
    if rejection:
        score -= 25
    if vol_spike:
        score += 25
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
        "score": score,
        "label": label
    }

# =========================
# CHARTS
# =========================
def make_chart(symbol):
    data = get_data(symbol, "1Min")

    if not data:
        return None

    close, high, vol = data

    plt.figure(figsize=(10,4))
    plt.plot(close)

    plt.axhline(max(close), linestyle="--", color="red")
    plt.axhline(min(close), linestyle="--", color="green")

    plt.title(symbol)

    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()

    return buf

# =========================
# DISCORD BOT
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
        await i.response.send_message("❌ No data available (market closed or Alpaca issue)")
        return

    await i.response.send_message(
        f"📊 {ticker}\n{d['label']}\n"
        f"Price: {d['price']}\nScore: {d['score']}"
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

    # 🔥 FIX: never empty Discord message
    if not out:
        await i.followup.send("❌ No market data available")
        return

    await i.followup.send("\n".join(out))

@bot.tree.command(name="chart")
async def chart(i: discord.Interaction, ticker: str):
    await i.response.defer()

    img = make_chart(ticker.upper())

    if not img:
        await i.followup.send("❌ No chart data available")
        return

    file = discord.File(img, filename="chart.png")
    await i.followup.send(file=file)

@bot.tree.command(name="help")
async def help(i: discord.Interaction):
    await i.response.send_message(
        "/rate - analyze stock\n"
        "/scan - scan market\n"
        "/chart - show chart\n"
        "/modes - trading modes\n"
    )

@bot.tree.command(name="modes")
async def modes(i: discord.Interaction):
    await i.response.send_message(
        "modes: swing | daytrade | scalp"
    )

# =========================
# RUN
# =========================
bot.run(TOKEN)
