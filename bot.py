import os
import discord
from discord import app_commands
import requests
import statistics
from datetime import datetime

# =========================
# ENV
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

GUILD_ID = 1516963264486183053
BASE_URL = "https://data.alpaca.markets/v2"

alpaca_enabled = bool(ALPACA_KEY and ALPACA_SECRET)

headers = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET
} if alpaca_enabled else {}

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

# =========================
# BOT SETUP (FIXED PROPERLY)
# =========================

intents = discord.Intents.default()
class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

bot = Bot()

user_modes = {}
watchlists = {}

# =========================
# MARKET STATE
# =========================

def market_open():
    now = datetime.utcnow()
    return 13 <= now.hour <= 20  # simple NY window (good enough for v1)

# =========================
# DATA ROUTER (KEY FIX)
# =========================

def get_alpaca(symbol):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"
        params = {"timeframe": "1Min", "limit": 120, "feed": "iex"}

        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            return None

        data = r.json().get("bars", [])
        if not data:
            return None

        c, h, l, v = [], [], [], []

        for b in data:
            c.append(b["c"])
            h.append(b["h"])
            l.append(b["l"])
            v.append(b["v"])

        if len(c) < 20:
            return None

        return c, h, l, v

    except:
        return None


# 🟡 YAHOO FALLBACK (NO yfinance dependency)
def get_yahoo(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            return None

        data = r.json()["chart"]["result"][0]
        closes = data["indicators"]["quote"][0]["close"]
        highs = data["indicators"]["quote"][0]["high"]
        lows = data["indicators"]["quote"][0]["low"]
        vols = data["indicators"]["quote"][0]["volume"]

        # clean None values
        closes = [x for x in closes if x is not None]
        highs = [x for x in highs if x is not None]
        lows = [x for x in lows if x is not None]
        vols = [x for x in vols if x is not None]

        if len(closes) < 20:
            return None

        return closes, highs, lows, vols

    except:
        return None


def get_data(symbol):
    # PRIMARY
    if market_open():
        data = get_alpaca(symbol)
        if data:
            return data

    # FALLBACK
    data = get_yahoo(symbol)
    if data:
        return data

    return None


# =========================
# INDICATORS
# =========================

def indicators(c, h, l, v):
    tp_vol = sum(((h[i]+l[i]+c[i])/3)*v[i] for i in range(len(c)))
    vol = sum(v)

    vwap = tp_vol / vol if vol else c[-1]

    gains = [max(c[i]-c[i-1], 0) for i in range(1, len(c))]
    losses = [max(c[i-1]-c[i], 0) for i in range(1, len(c))]

    avg_gain = sum(gains[-14:]) / 14 if gains else 0
    avg_loss = sum(losses[-14:]) / 14 if losses else 1

    rs = avg_gain / avg_loss if avg_loss else 100
    rsi = 100 - (100 / (1 + rs))

    macd = statistics.mean(c[-12:]) - statistics.mean(c[-26:]) if len(c) >= 26 else 0

    return vwap, rsi, macd


def levels(h, l):
    return min(l[-50:]), max(h[-50:])


def score(c, h, l, v):
    price = c[-1]
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    s = 50

    s += 15 if price > vwap else -15
    s += 10 if rsi > 70 else -10 if rsi < 30 else 0
    s += 15 if macd > 0 else -15
    s += 20 if price > resistance * 0.995 else 0

    s = max(0, min(100, s))

    if s >= 80:
        sig = "🔥 STRONG BUY"
    elif s >= 65:
        sig = "⚡ BUY"
    elif s <= 25:
        sig = "❄ STRONG SELL"
    elif s <= 40:
        sig = "⚡ SELL"
    else:
        sig = "⏸ NO TRADE"

    return s, sig, vwap, rsi, macd, support, resistance


# =========================
# COMMANDS (STABLE SYNC FIX)
# =========================

@bot.tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(i: discord.Interaction):
    await i.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

    out = []

    for t in tickers:
        data = get_data(t)

        if not data:
            out.append(f"{t}: NO DATA (market closed or API fail)")
            continue

        c, h, l, v = data
        sc, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({sc}/100)")

    await i.followup.send("\n".join(out))


@bot.tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_data(symbol)
    if not data:
        await i.followup.send("No data available (Alpaca + Yahoo failed)")
        return

    c, h, l, v = data
    sc, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    await i.followup.send(
        f"📊 {symbol}\n{sig} ({sc}/100)\nVWAP: {vwap:.2f}\nRSI: {rsi:.1f}\nMACD: {macd:.3f}"
    )


@bot.tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_data(symbol)
    if not data:
        await i.followup.send("No data available")
        return

    c, h, l, v = data
    _, resistance = levels(h, l)

    if c[-1] > resistance * 0.995:
        await i.followup.send(f"🚀 {symbol} BREAKOUT")
    else:
        await i.followup.send(f"📉 {symbol} below resistance")


@bot.tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode(i: discord.Interaction, mode: str):
    user_modes[i.user.id] = mode
    await i.response.send_message(f"Mode set → {mode}")


# =========================
# SYNC FIX (THIS FIXES YOUR MISSING COMMANDS)
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    bot.tree.clear_commands(guild=guild)
    await bot.tree.sync(guild=guild)

    print("Guild sync success")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


bot.run(DISCORD_TOKEN)
