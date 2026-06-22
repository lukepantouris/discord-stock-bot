import os
import discord
from discord.ext import commands
import aiohttp
import statistics
import yfinance as yf

# =========================
# CONFIG
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1516963264486183053

ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

alpaca_enabled = bool(ALPACA_KEY and ALPACA_SECRET)

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

BASE_URL = "https://data.alpaca.markets/v2"

# =========================
# BOT CORE
# =========================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# STATE
# =========================

user_modes = {}

MODES = ["investing", "swing", "day", "scalp"]

# =========================
# UNIVERSE
# =========================

TICKERS = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AMD",
    "SPY","QQQ","IWM",
    "JPM","BAC","WFC","GS",
    "XOM","CVX",
    "UNH","PFE","JNJ",
    "COST","WMT","HD",
    "INTC","QCOM","ORCL","ADBE",
    "PLTR","SOFI","RIVN"
]

# =========================
# MODE
# =========================

def get_mode(uid):
    return user_modes.get(uid, "swing")

# =========================
# DATA HELPERS
# =========================

async def fetch_json(session, url, params=None):
    try:
        async with session.get(url, params=params, timeout=8) as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

# =========================
# ALPACA (SCALP / DAY ONLY)
# =========================

async def alpaca_data(symbol):
    url = f"{BASE_URL}/stocks/{symbol}/bars"

    headers = {}
    if alpaca_enabled:
        headers = {
            "APCA-API-KEY-ID": ALPACA_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET
        }

    async with aiohttp.ClientSession(headers=headers) as session:
        data = await fetch_json(session, url, {
            "timeframe": "1Min",
            "limit": 120,
            "feed": "iex"
        })

    if not data:
        return None

    bars = data.get("bars", [])
    if not bars or len(bars) < 30:
        return None

    return (
        [b["c"] for b in bars],
        [b["h"] for b in bars],
        [b["l"] for b in bars],
        [b["v"] for b in bars],
    )

# =========================
# YAHOO (STABLE TIMEFRAME ENGINE)
# =========================

async def yahoo_data(symbol, mode):
    try:
        t = yf.Ticker(symbol)

        if mode == "investing":
            df = t.history(period="6mo", interval="1d")

        elif mode == "swing":
            df = t.history(period="3mo", interval="1h")

        elif mode == "day":
            df = t.history(period="5d", interval="15m")

        elif mode == "scalp":
            return None  # scalp ONLY Alpaca

        else:
            df = t.history(period="1mo", interval="1h")

        if df is None or len(df) < 30:
            return None

        return (
            df["Close"].tolist(),
            df["High"].tolist(),
            df["Low"].tolist(),
            df["Volume"].tolist(),
        )

    except:
        return None

# =========================
# MASTER DATA ENGINE (V15.2 FIX)
# =========================

async def get_data(symbol, mode):
    if mode in ["scalp", "day"] and alpaca_enabled:
        data = await alpaca_data(symbol)
        if data:
            return data

    return await yahoo_data(symbol, mode)

# =========================
# REGIME DETECTION
# =========================

def regime(c):
    short = statistics.mean(c[-10:])
    long = statistics.mean(c[-30:])

    if short > long * 1.01:
        return "bull"
    elif short < long * 0.99:
        return "bear"
    return "chop"

# =========================
# INDICATORS
# =========================

def indicators(c):
    vwap = sum(c) / len(c)

    gains = [max(c[i] - c[i-1], 0) for i in range(1, len(c))]
    losses = [max(c[i-1] - c[i], 0) for i in range(1, len(c))]

    avg_g = sum(gains[-14:]) / 14 if gains else 0
    avg_l = sum(losses[-14:]) / 14 if losses else 1

    rsi = 100 - (100 / (1 + (avg_g / avg_l)))

    return vwap, rsi

# =========================
# PATTERN ENGINE (UNCHANGED LOGIC)
# =========================

def detect_patterns(c, h, l):
    bull = []
    bear = []

    high = max(h[-20:])
    low = min(l[-20:])
    price = c[-1]

    mid = statistics.mean(c[-20:])

    if c[-1] > c[-5] > c[-10]:
        bull.append(("Uptrend Structure", 2))
    if c[-1] < c[-5] < c[-10]:
        bear.append(("Downtrend Structure", 2))

    if price > mid and c[-5] < mid:
        bull.append(("Bull Flag Breakout", 3))

    if price < mid and c[-5] > mid:
        bear.append(("Bear Flag Breakdown", 3))

    if price >= high * 0.995:
        bull.append(("Ascending Pressure Breakout", 3))

    if price <= low * 0.005:
        bear.append(("Descending Breakdown", 3))

    if abs(c[-1] - max(c[-10:-2])) / price < 0.01:
        bear.append(("Double Top Risk", 2))

    if abs(c[-1] - min(c[-10:-2])) / price < 0.01:
        bull.append(("Double Bottom Setup", 2))

    return bull, bear

# =========================
# SCORING ENGINE (STABLE)
# =========================

def score(c, h, l, v, mode):
    vwap, rsi = indicators(c)
    reg = regime(c)

    price = c[-1]

    bull = 0
    bear = 0

    bull += 1 if price > vwap else 0
    bear += 1 if price < vwap else 0

    bull += 2 if rsi < 45 else 0
    bear += 2 if rsi > 55 else 0

    if reg == "bull":
        bull *= 1.2
    elif reg == "bear":
        bear *= 1.2

    if mode == "investing":
        bear *= 1.1
    elif mode == "scalp":
        bull *= 1.2
        bear *= 1.2

    score = 50 + (bull - bear) * 10
    score = max(0, min(100, score))

    if score >= 70:
        sig = "📈 LONG SETUP"
    elif score <= 40:
        sig = "📉 SHORT SETUP"
    else:
        sig = "⏸ NO TRADE"

    return score, sig, reg

# =========================
# COMMANDS
# =========================

@bot.tree.command(name="scan", description="Scan market", guild=discord.Object(id=GUILD_ID))
async def scan(interaction):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)

    longs = []
    shorts = []

    for t in TICKERS:
        data = await get_data(t, mode)
        if not data:
            continue

        c, h, l, v = data

        s, sig, reg = score(c, h, l, v, mode)
        bull_p, bear_p = detect_patterns(c, h, l)

        bull_score = sum(x[1] for x in bull_p)
        bear_score = sum(x[1] for x in bear_p)

        final_bull = s + bull_score * 2
        final_bear = (100 - s) + bear_score * 2

        if final_bull > final_bear:
            longs.append((t, final_bull))
        else:
            shorts.append((t, final_bear))

    longs.sort(key=lambda x: x[1], reverse=True)
    shorts.sort(key=lambda x: x[1], reverse=True)

    msg = f"MODE: {mode} | REGIME: {reg}\n\n📈 LONGS\n"

    for t, s in longs[:5]:
        msg += f"{t}: {int(s)}\n"

    msg += "\n📉 SHORTS\n"

    for t, s in shorts[:5]:
        msg += f"{t}: {int(s)}\n"

    await interaction.followup.send(msg)

# =========================
# MODE COMMAND
# =========================

@bot.tree.command(name="mode", description="Set mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(interaction, mode: str):
    mode = mode.lower()
    if mode not in MODES:
        return await interaction.response.send_message("investing / swing / day / scalp")

    user_modes[interaction.user.id] = mode
    await interaction.response.send_message(f"Mode → {mode}")

# =========================
# START
# =========================

@bot.event
async def setup_hook():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

bot.run(DISCORD_TOKEN)
