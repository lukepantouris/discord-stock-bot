import os
import discord
from discord.ext import commands
import json
import requests

# =========================
# TOKEN
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("TOKEN NOT FOUND")
    exit()

# =========================
# ALPACA CONFIG
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
# FETCH 1m DATA (ALPACA)
# =========================
def get_data(symbol, timeframe="1Min"):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars?timeframe={timeframe}&limit=50"
        r = requests.get(url, headers=headers)
        data = r.json()

        bars = data.get("bars", [])
        if not bars:
            return None

        closes = [b["c"] for b in bars]
        highs = [b["h"] for b in bars]
        volumes = [b["v"] for b in bars]

        return closes, highs, volumes

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

    retest = False
    if len(close) > 10:
        broke = max(close[-10:]) > resistance
        retest = broke and abs(price - resistance) / resistance < 0.005

    vol_spike = vol[-1] > (sum(vol[-20:]) / 20) * 1.8

    change = ((close[-1] - close[-5]) / close[-5]) * 100

    score = 0

    # =========================
    # MODE SYSTEM (1 MIN TRADING)
    # =========================

    if mode == "scalp":
        breakout_w = 50
        retest_w = 40
        reject_w = -50

    elif mode == "daytrade":
        breakout_w = 60
        retest_w = 50
        reject_w = -40

    elif mode == "swing":
        breakout_w = 65
        retest_w = 55
        reject_w = -35

    else:
        breakout_w = 50
        retest_w = 45
        reject_w = -30

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

    # =========================
    # LABEL
    # =========================
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
        "change": round(change, 2),
        "score": score,
        "label": label
    }

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
        f"📊 {ticker.upper()}\n"
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

@bot.tree.command(name="modes")
async def modes(i: discord.Interaction):
    await i.response.send_message(
        "swing - normal trades\n"
        "daytrade - intraday setups (5m-1m)\n"
        "scalp - fast moves (1m)\n"
    )

@bot.tree.command(name="setmode")
async def setmode(i: discord.Interaction, mode: str):
    u = user(str(i.user.id))

    mode = mode.lower()
    if mode not in ["swing","daytrade","scalp"]:
        await i.response.send_message("Invalid mode")
        return

    u["mode"] = mode
    save(memory)

    await i.response.send_message(f"Mode set to {mode}")

@bot.tree.command(name="help")
async def help(i: discord.Interaction):
    await i.response.send_message(
        "/rate ticker\n"
        "/scan\n"
        "/modes\n"
        "/setmode swing/daytrade/scalp\n"
        "/help"
    )

# =========================
# RUN
# =========================
bot.run(TOKEN)
