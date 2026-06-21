import os
import discord
from discord.ext import commands
import aiohttp
import statistics
import yfinance as yf
import asyncio

# =========================
# CONFIG
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1516963264486183053
ADMIN_ID = 1478514616718856244

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

# =========================
# BOT CORE
# =========================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# STATE
# =========================

user_modes = {}
watchlists = {}
price_cache = {}

MODES = ["investing", "swing", "day", "scalp"]

# =========================
# UNIVERSE (safe for 512MB)
# =========================

TICKERS = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AMD","AVGO","NFLX",
    "SPY","QQQ","IWM",
    "JPM","BAC","WFC","GS",
    "XOM","CVX",
    "UNH","PFE","JNJ",
    "COST","WMT","HD","TGT",
    "INTC","QCOM","ORCL","ADBE",
    "PLTR","SOFI","RIVN","UBER","LYFT"
]

# =========================
# MODE
# =========================

def get_mode(uid):
    return user_modes.get(uid, "swing")

# =========================
# DATA
# =========================

async def yahoo(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1d", interval="5m")

        if df is None or len(df) < 25:
            return None

        return (
            df["Close"].tolist(),
            df["High"].tolist(),
            df["Low"].tolist(),
            df["Volume"].tolist(),
        )
    except:
        return None

async def get_data(symbol):
    return await yahoo(symbol)

# =========================
# INDICATORS
# =========================

def indicators(c, h, l, v):
    vwap = sum(c) / len(c)

    gains = []
    losses = []

    for i in range(1, len(c)):
        diff = c[i] - c[i-1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_g = sum(gains[-14:]) / 14 if gains else 0
    avg_l = sum(losses[-14:]) / 14 if losses else 1

    rsi = 100 - (100 / (1 + (avg_g / avg_l)))

    macd = statistics.mean(c[-12:]) - statistics.mean(c[-26:]) if len(c) >= 26 else 0

    return vwap, rsi, macd

# =========================
# MARKET REGIME (NEW IN V13)
# =========================

def market_regime(c):
    short = statistics.mean(c[-10:])
    long = statistics.mean(c[-30:]) if len(c) >= 30 else short

    if short > long * 1.01:
        return "bull"
    elif short < long * 0.99:
        return "bear"
    else:
        return "chop"

# =========================
# PATTERN ENGINE (REAL V13)
# =========================

def detect_patterns(c, h, l):
    patterns = {"bull": [], "bear": []}

    high = max(h[-20:])
    low = min(l[-20:])
    price = c[-1]

    # Trend
    if c[-1] > c[-5] > c[-10]:
        patterns["bull"].append("Momentum Uptrend")
    if c[-1] < c[-5] < c[-10]:
        patterns["bear"].append("Momentum Downtrend")

    # Breakouts
    if price >= high * 0.995:
        patterns["bull"].append("Breakout High")
    if price <= low * 1.005:
        patterns["bear"].append("Breakdown Low")

    # Mean reversion signals
    mean = statistics.mean(c[-20:])
    if price > mean:
        patterns["bull"].append("Above Mean Strength")
    else:
        patterns["bear"].append("Below Mean Weakness")

    # Simple structure patterns
    if c[-1] > c[-3] and c[-3] < c[-6]:
        patterns["bull"].append("Local Reversal Up")
    if c[-1] < c[-3] and c[-3] > c[-6]:
        patterns["bear"].append("Local Reversal Down")

    return patterns

# =========================
# SCORING ENGINE (FIXED BALANCE)
# =========================

def score(c, h, l, v, mode):
    vwap, rsi, macd = indicators(c, h, l, v)
    regime = market_regime(c)

    price = c[-1]

    bull = 0
    bear = 0

    # BASE
    bull += 1 if price > vwap else 0
    bear += 1 if price < vwap else 0

    bull += 2 if macd > 0 else 0
    bear += 2 if macd < 0 else 0

    # RSI logic
    if rsi < 40:
        bull += 2
    elif rsi > 60:
        bear += 2

    # MODE ADJUSTMENTS
    if mode == "investing":
        bull *= 0.9
        bear *= 1.1
    elif mode == "day":
        bull *= 1.1
        bear *= 1.1
    elif mode == "scalp":
        bull *= 1.25
        bear *= 1.25

    # REGIME FILTER
    if regime == "bull":
        bull *= 1.2
    elif regime == "bear":
        bear *= 1.2

    score = 50 + (bull - bear) * 12
    score = max(0, min(100, score))

    if score >= 70:
        sig = "📈 LONG SETUP"
    elif score <= 40:
        sig = "📉 SHORT SETUP"
    else:
        sig = "⏸ NO TRADE"

    return score, sig, regime

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
        data = await get_data(t)
        if not data:
            continue

        c, h, l, v = data
        s, sig, regime = score(c, h, l, v, mode)

        if s >= 60:
            longs.append((t, s))
        elif s <= 40:
            shorts.append((t, s))

    longs.sort(key=lambda x: x[1], reverse=True)
    shorts.sort(key=lambda x: x[1])

    msg = f"MODE: {mode}\nREGIME: {regime}\n\n📈 LONGS\n"

    for t, s in longs[:5]:
        msg += f"{t}: {int(s)}\n"

    msg += "\n📉 SHORTS\n"

    for t, s in shorts[:5]:
        msg += f"{t}: {int(s)}\n"

    await interaction.followup.send(msg)

@bot.tree.command(name="longs", description="Top longs", guild=discord.Object(id=GUILD_ID))
async def longs(interaction):
    await scan(interaction)

@bot.tree.command(name="shorts", description="Top shorts", guild=discord.Object(id=GUILD_ID))
async def shorts(interaction):
    await scan(interaction)

@bot.tree.command(name="pattern", description="Detect patterns", guild=discord.Object(id=GUILD_ID))
async def pattern(interaction, symbol: str):
    await interaction.response.defer()

    data = await get_data(symbol)
    if not data:
        return await interaction.followup.send("No data")

    c, h, l, v = data
    p = detect_patterns(c, h, l)

    await interaction.followup.send(
        f"{symbol}\nBULL: {', '.join(p['bull'])}\nBEAR: {', '.join(p['bear'])}"
    )

@bot.tree.command(name="mode", description="Set mode", guild=discord.Object(id=GUILD_ID))
async def mode(interaction, mode: str):
    mode = mode.lower()
    if mode not in MODES:
        return await interaction.response.send_message("investing / swing / day / scalp")

    user_modes[interaction.user.id] = mode
    await interaction.response.send_message(f"Mode → {mode}")

# =========================
# SYNC
# =========================

@bot.event
async def setup_hook():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

bot.run(DISCORD_TOKEN)
