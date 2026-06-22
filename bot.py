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

last_scores = {}  # V16 stability layer

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
# DATA
# =========================

async def yahoo(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1d", interval="5m")

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
# MODE
# =========================

def get_mode(uid):
    return user_modes.get(uid, "swing")


# =========================
# REGIME
# =========================

def regime(c):
    short = statistics.mean(c[-10:])
    long = statistics.mean(c[-30:])

    if short > long * 1.01:
        return "bull"
    elif short < long * 0.99:
        return "bear"
    return "chop"


def market_bias(reg):
    if reg == "bull":
        return 1.1, 0.95
    if reg == "bear":
        return 0.95, 1.1
    return 1.0, 1.0


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
# V17 EXPLANATION ENGINE (NEW)
# =========================

def explain(c, h, l):
    bull = []
    bear = []

    vwap = sum(c) / len(c)
    price = c[-1]

    if price > vwap:
        bull.append("Price above VWAP (momentum bullish)")
    else:
        bear.append("Price below VWAP (bearish pressure)")

    if c[-1] > c[-5] > c[-10]:
        bull.append("Uptrend structure confirmed")

    gains = [max(c[i] - c[i-1], 0) for i in range(1, len(c))]
    losses = [max(c[i-1] - c[i], 0) for i in range(1, len(c))]

    avg_g = sum(gains[-14:]) / 14 if gains else 0
    avg_l = sum(losses[-14:]) / 14 if losses else 1

    rsi = 100 - (100 / (1 + (avg_g / avg_l)))

    if rsi < 45:
        bull.append("RSI oversold bounce zone")
    elif rsi > 55:
        bear.append("RSI overbought pressure")

    return bull, bear


# =========================
# STABILITY LAYER (V16 FIX)
# =========================

def stabilize(symbol, score):
    old = last_scores.get(symbol)
    if old is None:
        last_scores[symbol] = score
        return score

    smoothed = (old * 0.65) + (score * 0.35)
    last_scores[symbol] = smoothed
    return smoothed


# =========================
# DATA WRAPPER
# =========================

async def get_data(symbol):
    return await yahoo(symbol)


# =========================
# SCORE ENGINE
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

    bull_mult, bear_mult = market_bias(reg)
    bull *= bull_mult
    bear *= bear_mult

    if mode == "investing":
        bear *= 1.05
    elif mode == "scalp":
        bull *= 1.15
        bear *= 1.15

    score = 50 + (bull - bear) * 10
    score = max(0, min(100, score))

    return score, reg


# =========================
# COMMANDS (ALL KEPT)
# =========================

@bot.tree.command(name="scan", description="Scan market", guild=discord.Object(id=GUILD_ID))
async def scan(interaction):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)

    longs = []
    shorts = []

    async def process(t):
        data = await get_data(t)
        if not data:
            return None

        c, h, l, v = data

        s, reg = score(c, h, l, v, mode)
        bull_p, bear_p = detect_patterns(c, h, l)
        bull_ex, bear_ex = explain(c, h, l)

        bull_score = sum(x[1] for x in bull_p)
        bear_score = sum(x[1] for x in bear_p)

        final_bull = stabilize(t, s + bull_score * 2)
        final_bear = stabilize(t + "_b", (100 - s) + bear_score * 2)

        return t, final_bull, final_bear, bull_ex, bear_ex

    tasks = [process(t) for t in TICKERS]
    results = await asyncio.gather(*tasks)

    for r in results:
        if not r:
            continue

        t, fb, fs, bull_ex, bear_ex = r

        if fb > fs:
            longs.append((t, fb, bull_ex))
        else:
            shorts.append((t, fs, bear_ex))

    longs.sort(key=lambda x: x[1], reverse=True)
    shorts.sort(key=lambda x: x[1], reverse=True)

    msg = f"MODE: {mode} | V17 ENGINE\n\n📈 LONGS\n"

    for t, s, why in longs[:5]:
        msg += f"\n{t}: {int(s)}\nWHY:\n- " + "\n- ".join(why[:3]) + "\n"

    msg += "\n📉 SHORTS\n"

    for t, s, why in shorts[:5]:
        msg += f"\n{t}: {int(s)}\nWHY:\n- " + "\n- ".join(why[:3]) + "\n"

    await interaction.followup.send(msg)


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
