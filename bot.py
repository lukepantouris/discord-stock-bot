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

ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

GUILD_ID = 1516963264486183053
BASE_URL = "https://data.alpaca.markets/v2"

alpaca_enabled = bool(ALPACA_KEY and ALPACA_SECRET)

HEADERS = {}
if alpaca_enabled:
    HEADERS = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }

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

TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

MODES = ["investing", "swing", "day", "scalp"]

# =========================
# MODE SYSTEM
# =========================

def get_mode(uid):
    return user_modes.get(uid, "swing")

def apply_mode(mode, score):
    if mode == "investing":
        return score * 0.85
    if mode == "swing":
        return score
    if mode == "day":
        return score * 1.1
    if mode == "scalp":
        return score * 1.25
    return score

# =========================
# DATA
# =========================

async def fetch_json(session, url, params=None):
    try:
        async with session.get(url, headers=HEADERS, params=params, timeout=6) as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

async def alpaca(session, symbol):
    url = f"{BASE_URL}/stocks/{symbol}/bars"

    data = await fetch_json(session, url, {
        "timeframe": "1Min",
        "limit": 120,
        "feed": "iex"
    })

    if not data:
        return None

    bars = data.get("bars", [])
    if not bars:
        return None

    return (
        [b["c"] for b in bars],
        [b["h"] for b in bars],
        [b["l"] for b in bars],
        [b["v"] for b in bars],
    )

async def yahoo(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1d", interval="1m")

        if df is None or len(df) < 20:
            return None

        return (
            df["Close"].tolist(),
            df["High"].tolist(),
            df["Low"].tolist(),
            df["Volume"].tolist(),
        )
    except:
        return None

async def get_data(session, symbol):
    data = None

    if alpaca_enabled:
        data = await alpaca(session, symbol)

    if not data:
        data = await yahoo(symbol)

    return data

# =========================
# INDICATORS
# =========================

def indicators(c, h, l, v):
    tp = [(h[i] + l[i] + c[i]) / 3 for i in range(len(c))]
    vwap = sum(tp[i] * v[i] for i in range(len(c))) / sum(v) if sum(v) else c[-1]

    gains, losses = [], []

    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        if d > 0:
            gains.append(d)
        else:
            losses.append(abs(d))

    avg_g = sum(gains[-14:]) / 14 if gains else 0
    avg_l = sum(losses[-14:]) / 14 if losses else 1

    rs = avg_g / avg_l if avg_l else 100
    rsi = 100 - (100 / (1 + rs))

    macd = statistics.mean(c[-12:]) - statistics.mean(c[-26:]) if len(c) >= 26 else 0

    return vwap, rsi, macd

def levels(h, l):
    return min(l[-50:]), max(h[-50:])

def breakout(price, resistance):
    return price > resistance * 0.995

# =========================
# SCORING
# =========================

def score(c, h, l, v, mode):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]
    s = 50

    s += 15 if price > vwap else -15
    s += 10 if rsi > 70 else -10 if rsi < 30 else 0
    s += 15 if macd > 0 else -15

    if breakout(price, resistance):
        s += 20

    s = apply_mode(mode, s)
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
        sig = "⏸ HOLD"

    return s, sig, vwap, rsi, macd, support, resistance

# =========================
# COMMANDS
# =========================

@bot.tree.command(name="help", description="Commands", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction):
    await interaction.response.send_message(
        "/mode /scan /opportunities /scalp /breakout /watch /watchlist /detail"
    )

@bot.tree.command(name="mode", description="Set mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(interaction, mode: str):
    mode = mode.lower()

    if mode not in MODES:
        return await interaction.response.send_message(
            "Modes:\ninvesting\nswing\nday\nscalp"
        )

    user_modes[interaction.user.id] = mode
    await interaction.response.send_message(f"Mode set → {mode}")

# -------------------------
# SCAN
# -------------------------

@bot.tree.command(name="scan", description="Market scan", guild=discord.Object(id=GUILD_ID))
async def scan_cmd(interaction):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)
    results = []

    async with aiohttp.ClientSession() as session:
        for t in TICKERS:
            data = await get_data(session, t)
            if not data:
                results.append(f"{t}: NO DATA")
                continue

            c, h, l, v = data
            s, sig, *_ = score(c, h, l, v, mode)

            results.append(f"{t}: {sig} ({int(s)})")

    await interaction.followup.send(
        f"MODE: {mode}\n\n" + "\n".join(results)
    )

# -------------------------
# OPPORTUNITIES
# -------------------------

@bot.tree.command(name="opportunities", description="Top setups", guild=discord.Object(id=GUILD_ID))
async def opp_cmd(interaction):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)
    results = []

    async with aiohttp.ClientSession() as session:
        for t in TICKERS:
            data = await get_data(session, t)
            if not data:
                continue

            c, h, l, v = data
            s, sig, *_ = score(c, h, l, v, mode)

            if s >= 70:
                results.append(f"{t}: {sig} ({int(s)})")

    if not results:
        return await interaction.followup.send("No setups")

    await interaction.followup.send("\n".join(results))

# -------------------------
# SCALP
# -------------------------

@bot.tree.command(name="scalp", description="Quick signal", guild=discord.Object(id=GUILD_ID))
async def scalp_cmd(interaction, symbol: str):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)

    async with aiohttp.ClientSession() as session:
        data = await get_data(session, symbol)

    if not data:
        return await interaction.followup.send("No data")

    c, h, l, v = data
    s, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v, mode)

    await interaction.followup.send(
        f"{symbol}\n{sig} ({int(s)})\nVWAP {vwap:.2f}\nRSI {rsi:.1f}"
    )

# -------------------------
# DETAIL
# -------------------------

@bot.tree.command(name="detail", description="Full breakdown", guild=discord.Object(id=GUILD_ID))
async def detail_cmd(interaction, symbol: str):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)

    async with aiohttp.ClientSession() as session:
        data = await get_data(session, symbol)

    if not data:
        return await interaction.followup.send("No data")

    c, h, l, v = data
    s, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v, mode)

    await interaction.followup.send(
        f"{symbol} DETAIL\n{sig} ({int(s)})\nVWAP {vwap:.2f}\nRSI {rsi:.1f}"
    )

# -------------------------
# WATCHLIST
# -------------------------

@bot.tree.command(name="watch", description="Add watchlist", guild=discord.Object(id=GUILD_ID))
async def watch_cmd(interaction, symbol: str):
    watchlists.setdefault(interaction.user.id, [])
    if symbol not in watchlists[interaction.user.id]:
        watchlists[interaction.user.id].append(symbol)

    await interaction.response.send_message(f"Added {symbol}")

@bot.tree.command(name="watchlist", description="View watchlist", guild=discord.Object(id=GUILD_ID))
async def watchlist_cmd(interaction):
    items = watchlists.get(interaction.user.id, [])
    if not items:
        return await interaction.response.send_message("Empty")

    await interaction.response.send_message("\n".join(items))

# =========================
# RESET COMMAND (YOUR REQUEST)
# =========================

@bot.tree.command(name="reset_commands", description="CLEAR OLD COMMANDS", guild=discord.Object(id=GUILD_ID))
async def reset_commands(interaction):
    await interaction.response.defer()

    try:
        guild = discord.Object(id=GUILD_ID)

        bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
        synced = await bot.tree.sync(guild=guild)

        await interaction.followup.send(
            "RESET COMPLETE. Restart bot.\n"
            + ", ".join([c.name for c in synced])
        )

    except Exception as e:
        await interaction.followup.send(str(e))

# =========================
# SYNC
# =========================

@bot.event
async def setup_hook():
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("SYNC OK:", [c.name for c in synced])
    except Exception as e:
        print("SYNC ERROR:", e)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
