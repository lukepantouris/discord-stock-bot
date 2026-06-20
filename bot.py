import os
import discord
from discord import app_commands
import requests
import statistics
import asyncio
import yfinance as yf

# =========================
# ENV
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

GUILD_ID = 1516963264486183053
BASE_URL = "https://data.alpaca.markets/v2"

alpaca_enabled = bool(ALPACA_KEY and ALPACA_SECRET)

headers = {}
if alpaca_enabled:
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

# =========================
# BOT (CORRECT METHOD)
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

user_modes = {}
watchlists = {}

# =========================
# DATA ENGINE (ALPACA + YAHOO FALLBACK)
# =========================

async def fetch_yahoo(symbol):
    try:
        t = yf.Ticker(symbol)
        data = t.history(period="1d", interval="1m")

        if data is None or len(data) < 20:
            return None

        c = data["Close"].tolist()
        h = data["High"].tolist()
        l = data["Low"].tolist()
        v = data["Volume"].tolist()

        return c, h, l, v

    except:
        return None


async def fetch_alpaca(symbol):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": "1Min",
            "limit": 120,
            "feed": "iex"
        }

        r = requests.get(url, headers=headers, params=params, timeout=8)

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


async def get_data(symbol):
    # TRY ALPACA FIRST
    if alpaca_enabled:
        data = await fetch_alpaca(symbol)
        if data:
            return data

    # FALLBACK YAHOO
    return await fetch_yahoo(symbol)

# =========================
# INDICATORS
# =========================

def indicators(c, h, l, v):
    tp = [(h[i] + l[i] + c[i]) / 3 for i in range(len(c))]
    vwap = sum(tp[i] * v[i] for i in range(len(c))) / sum(v) if sum(v) else c[-1]

    gains = []
    losses = []

    for i in range(1, len(c)):
        diff = c[i] - c[i - 1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains[-14:]) / 14 if gains else 0
    avg_loss = sum(losses[-14:]) / 14 if losses else 1

    rs = avg_gain / avg_loss if avg_loss else 100
    rsi = 100 - (100 / (1 + rs))

    macd = statistics.mean(c[-12:]) - statistics.mean(c[-26:]) if len(c) >= 26 else 0

    return vwap, rsi, macd

# =========================
# LEVELS
# =========================

def levels(h, l):
    return min(l[-50:]), max(h[-50:])

def breakout(price, resistance):
    return price > resistance * 0.995

# =========================
# SCORING ENGINE
# =========================

def score(c, h, l, v):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]
    s = 50

    if price > vwap:
        s += 15
    else:
        s -= 15

    if rsi > 70:
        s += 10
    elif rsi < 30:
        s -= 10

    s += 15 if macd > 0 else -15

    if breakout(price, resistance):
        s += 20

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
# SAFE RESPONSE WRAPPER (FIXES "NOT RESPONDING")
# =========================

async def safe_reply(interaction, content):
    try:
        await interaction.followup.send(content)
    except:
        pass

# =========================
# COMMANDS
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(i: discord.Interaction):
    await i.response.send_message(
        "/scan /scalp /breakout /rate /besttrade /watch /mode"
    )

@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(i: discord.Interaction):
    await i.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = await get_data(t)

        if not data:
            out.append(f"{t}: NO DATA")
            continue

        c, h, l, v = data
        sc, sig, *_ = score(c, h, l, v)
        out.append(f"{t}: {sig} ({sc}/100)")

    await safe_reply(i, "\n".join(out))


@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = await get_data(symbol)

    if not data:
        await safe_reply(i, "No data available")
        return

    c, h, l, v = data
    sc, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    msg = f"""
{symbol}
{sig} ({sc}/100)

VWAP {vwap:.2f}
RSI {rsi:.1f}
MACD {macd:.2f}
Support {support:.2f}
Resistance {resistance:.2f}
"""

    await safe_reply(i, msg)


@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout_cmd(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = await get_data(symbol)

    if not data:
        await safe_reply(i, "No data")
        return

    c, h, l, v = data
    _, r = levels(h, l)

    msg = f"🚀 BREAKOUT {symbol}" if c[-1] > r * 0.995 else f"📉 {symbol} not breaking"

    await safe_reply(i, msg)


@tree.command(name="besttrade", guild=discord.Object(id=GUILD_ID))
async def besttrade(i: discord.Interaction):
    await i.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

    best = ("NONE", 0)
    out = []

    for t in tickers:
        data = await get_data(t)
        if not data:
            continue

        c, h, l, v = data
        sc, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({sc})")

        if sc > best[1]:
            best = (t, sc)

    out.append(f"\nBEST: {best[0]} ({best[1]}/100)")

    await safe_reply(i, "\n".join(out))


@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode(i: discord.Interaction, mode: str):
    user_modes[i.user.id] = mode
    await i.response.send_message(f"Mode set → {mode}")

@tree.command(name="watch", guild=discord.Object(id=GUILD_ID))
async def watch(i: discord.Interaction, symbol: str):
    uid = i.user.id
    watchlists.setdefault(uid, []).append(symbol.upper())
    await i.response.send_message(f"Watching {symbol}")

# =========================
# FIX COMMAND SYNC (CRITICAL FIX)
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    tree.clear_commands(guild=guild)
    tree.copy_global_to(guild=guild)

    await tree.sync(guild=guild)

    print("Guild sync success")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
