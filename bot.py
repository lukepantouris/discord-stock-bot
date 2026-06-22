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

MODES = ["investing", "swing", "day", "scalp"]

# =========================
# V15 ENGINE ROTATION
# =========================

UNIVERSES = {
    "investing": [
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","JPM","UNH","XOM","COST",
        "WMT","HD","JNJ","PFE"
    ],

    "swing": [
        "AAPL","MSFT","NVDA","TSLA","AMD","AMZN","META","NFLX","PLTR","SOFI",
        "QQQ","SPY","IWM","ADBE","ORCL","QCOM"
    ],

    "day": [
        "TSLA","NVDA","AMD","PLTR","SOFI","RIVN","META","AAPL","AMZN","NFLX"
    ],

    "scalp": [
        "TSLA","NVDA","AMD","PLTR","SOFI","RIVN"
    ]
}

# =========================
# MODE
# =========================

def get_mode(uid):
    return user_modes.get(uid, "swing")

# =========================
# DATA (timeframe rotation)
# =========================

async def get_data(symbol, mode):
    try:
        t = yf.Ticker(symbol)

        if mode == "investing":
            df = t.history(period="6mo", interval="1d")
        elif mode == "swing":
            df = t.history(period="1mo", interval="1h")
        elif mode == "day":
            df = t.history(period="5d", interval="15m")
        else:
            df = t.history(period="1d", interval="1m")

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
# PATTERNS
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
        bull.append(("Ascending Breakout", 3))
    if price <= low * 1.005:
        bear.append(("Descending Breakdown", 3))

    if abs(c[-1] - max(c[-10:-2])) / price < 0.01:
        bear.append(("Double Top Risk", 2))
    if abs(c[-1] - min(c[-10:-2])) / price < 0.01:
        bull.append(("Double Bottom Setup", 2))

    return bull, bear

# =========================
# SCORE
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

    final = 50 + (bull - bear) * 10
    final = max(0, min(100, final))

    if final >= 70:
        sig = "📈 LONG SETUP"
    elif final <= 40:
        sig = "📉 SHORT SETUP"
    else:
        sig = "⏸ NO TRADE"

    return final, sig, reg

# =========================
# COMMANDS (FULL RESTORE)
# =========================

@bot.tree.command(name="mode", description="Set mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(interaction, mode: str):
    mode = mode.lower()

    if mode not in MODES:
        return await interaction.response.send_message("investing / swing / day / scalp")

    user_modes[interaction.user.id] = mode
    await interaction.response.send_message(f"Mode → {mode}")

# -------------------------
# HELP
# -------------------------

@bot.tree.command(name="help", description="Commands", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction):
    await interaction.response.send_message(
        "/mode /scan /pattern /scalp /detail /watch /watchlist /opportunities"
    )

# -------------------------
# WATCHLIST
# -------------------------

@bot.tree.command(name="watch", description="Add watch", guild=discord.Object(id=GUILD_ID))
async def watch(interaction, symbol: str):
    uid = interaction.user.id
    watchlists.setdefault(uid, [])

    if symbol not in watchlists[uid]:
        watchlists[uid].append(symbol)

    await interaction.response.send_message(f"Watching {symbol}")

@bot.tree.command(name="watchlist", description="View watchlist", guild=discord.Object(id=GUILD_ID))
async def watchlist_cmd(interaction):
    items = watchlists.get(interaction.user.id, [])

    await interaction.response.send_message("\n".join(items) if items else "Empty")

# -------------------------
# SCAN
# -------------------------

@bot.tree.command(name="scan", description="Scan market", guild=discord.Object(id=GUILD_ID))
async def scan(interaction):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)

    longs = []
    shorts = []

    for t in UNIVERSES[mode]:
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

    msg = f"MODE: {mode}\n\n📈 LONGS\n"

    for t, s in longs[:5]:
        msg += f"{t}: {int(s)}\n"

    msg += "\n📉 SHORTS\n"

    for t, s in shorts[:5]:
        msg += f"{t}: {int(s)}\n"

    await interaction.followup.send(msg)

# -------------------------
# PATTERN
# -------------------------

@bot.tree.command(name="pattern", description="Pattern scan", guild=discord.Object(id=GUILD_ID))
async def pattern(interaction, symbol: str):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)
    data = await get_data(symbol, mode)

    if not data:
        return await interaction.followup.send("No data")

    c, h, l, v = data
    bull, bear = detect_patterns(c, h, l)

    bull_txt = "\n".join([f"✅ {x[0]}" for x in bull]) or "None"
    bear_txt = "\n".join([f"❌ {x[0]}" for x in bear]) or "None"

    await interaction.followup.send(
        f"{symbol}\n\nBULL PATTERNS:\n{bull_txt}\n\nBEAR PATTERNS:\n{bear_txt}"
    )

# -------------------------
# SCALP
# -------------------------

@bot.tree.command(name="scalp", description="Quick signal", guild=discord.Object(id=GUILD_ID))
async def scalp(interaction, symbol: str):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)
    data = await get_data(symbol, mode)

    if not data:
        return await interaction.followup.send("No data")

    c, h, l, v = data
    s, sig, reg = score(c, h, l, v, mode)

    await interaction.followup.send(f"{symbol}\n{sig} ({int(s)})\nREGIME: {reg}")

# -------------------------
# DETAIL
# -------------------------

@bot.tree.command(name="detail", description="Full breakdown", guild=discord.Object(id=GUILD_ID))
async def detail(interaction, symbol: str):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)
    data = await get_data(symbol, mode)

    if not data:
        return await interaction.followup.send("No data")

    c, h, l, v = data
    s, sig, reg = score(c, h, l, v, mode)

    await interaction.followup.send(
        f"{symbol}\n\n{sig} ({int(s)})\nREGIME: {reg}"
    )

# -------------------------
# OPPORTUNITIES
# -------------------------

@bot.tree.command(name="opportunities", description="Top setups", guild=discord.Object(id=GUILD_ID))
async def opp(interaction):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)

    results = []

    for t in UNIVERSES[mode]:
        data = await get_data(t, mode)
        if not data:
            continue

        c, h, l, v = data
        s, sig, reg = score(c, h, l, v, mode)

        if s >= 70:
            results.append(f"{t}: {sig} ({int(s)})")

    await interaction.followup.send("\n".join(results) if results else "No setups")

# =========================
# SYNC
# =========================

@bot.event
async def setup_hook():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
