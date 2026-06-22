import os
import discord
from discord.ext import commands
import aiohttp
import statistics
import yfinance as yf
import asyncio
import time

# =========================
# CONFIG
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1516963264486183053

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
MODES = ["investing", "swing", "day", "scalp"]

last_cache = {}  # V18 cache system
CACHE_TTL = 120  # 2 min refresh stability

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
# SAFE DATA LAYER (V18 FIX)
# =========================

async def yahoo(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="5d", interval="5m")

        if df is None or len(df) < 20:
            return None

        return (
            df["Close"].tolist(),
            df["High"].tolist(),
            df["Low"].tolist(),
            df["Volume"].tolist(),
        )

    except Exception as e:
        print(f"[YF ERROR] {symbol}: {e}")
        return None

# =========================
# CACHE SYSTEM (V18 CORE FIX)
# =========================

async def get_data(symbol):
    now = time.time()

    if symbol in last_cache:
        data, ts = last_cache[symbol]
        if now - ts < CACHE_TTL:
            return data

    data = await yahoo(symbol)

    if data:
        last_cache[symbol] = (data, now)

    return data

# =========================
# REGIME DETECTION
# =========================

def regime(c):
    if len(c) < 30:
        return "chop"

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
# PATTERNS (UNCHANGED CORE)
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

    if price <= low * 1.005:
        bear.append(("Descending Breakdown", 3))

    if abs(c[-1] - max(c[-10:-2])) / price < 0.01:
        bear.append(("Double Top Risk", 2))

    if abs(c[-1] - min(c[-10:-2])) / price < 0.01:
        bull.append(("Double Bottom Setup", 2))

    if c[-8] < c[-5] > c[-2] and c[-5] == max(c[-10:]):
        bear.append(("Head & Shoulders Risk", 3))

    if c[-8] > c[-5] < c[-2] and c[-5] == min(c[-10:]):
        bull.append(("Inverse H&S Setup", 3))

    if h[-1] < h[-5] and l[-1] > l[-5]:
        bull.append(("Falling Wedge Breakout Setup", 3))

    if h[-1] > h[-5] and l[-1] < l[-5]:
        bear.append(("Rising Wedge Breakdown Setup", 3))

    return bull, bear

# =========================
# EXPLANATION ENGINE
# =========================

def explain(c):
    bull = []
    bear = []

    vwap = sum(c) / len(c)
    price = c[-1]

    if price > vwap:
        bull.append("Price above VWAP → bullish momentum bias")
    else:
        bear.append("Price below VWAP → bearish pressure")

    if c[-1] > c[-5] > c[-10]:
        bull.append("Uptrend structure confirmed")

    return bull, bear

# =========================
# SCORING ENGINE
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
        bull *= 1.1
    elif reg == "bear":
        bear *= 1.1

    if mode == "investing":
        bear *= 1.05
    elif mode == "scalp":
        bull *= 1.1
        bear *= 1.1

    score = 50 + (bull - bear) * 10
    score = max(0, min(100, score))

    return score, reg

# =========================
# SCAN COMMAND (V18 FIXED OUTPUT)
# =========================

@bot.tree.command(name="scan", description="Scan market", guild=discord.Object(id=GUILD_ID))
async def scan(interaction):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)

    longs = []
    shorts = []
    failed = 0

    async def process(t):
        data = await get_data(t)
        if not data:
            return None

        c, h, l, v = data

        s, reg = score(c, h, l, v, mode)
        bull_p, bear_p = detect_patterns(c, h, l)
        bull_ex, bear_ex = explain(c)

        bull_score = sum(x[1] for x in bull_p)
        bear_score = sum(x[1] for x in bear_p)

        final_bull = s + bull_score * 2
        final_bear = (100 - s) + bear_score * 2

        if final_bull > final_bear:
            longs.append((t, final_bull, bull_ex))
        else:
            shorts.append((t, final_bear, bear_ex))

    tasks = [process(t) for t in TICKERS]
    results = await asyncio.gather(*tasks)

    for r in results:
        if not r:
            failed += 1

    longs.sort(key=lambda x: x[1], reverse=True)
    shorts.sort(key=lambda x: x[1], reverse=True)

    # =========================
    # OUTPUT (FIXED EMPTY BUG)
    # =========================

    msg = f"MODE: {mode} | V18 ENGINE\n"
    msg += f"ACTIVE: {len(TICKERS)-failed}/{len(TICKERS)}\n\n"

    msg += "📈 LONGS\n"
    if not longs:
        msg += "No strong long setups\n"
    else:
        for t, s, why in longs[:5]:
            msg += f"\n{t}: {int(s)}\nWHY:\n- " + "\n- ".join(why[:3]) + "\n"

    msg += "\n📉 SHORTS\n"
    if not shorts:
        msg += "No strong short setups\n"
    else:
        for t, s, why in shorts[:5]:
            msg += f"\n{t}: {int(s)}\nWHY:\n- " + "\n- ".join(why[:3]) + "\n"

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
