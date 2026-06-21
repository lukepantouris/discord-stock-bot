import os
import discord
from discord import app_commands
import requests
import asyncio
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

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

alpaca_enabled = bool(ALPACA_KEY and ALPACA_SECRET)

headers = {
    "APCA-API-KEY-ID": ALPACA_KEY or "",
    "APCA-API-SECRET-KEY": ALPACA_SECRET or ""
}

# =========================
# BOT SETUP (FIXED PROPER TREE SYSTEM)
# =========================

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# =========================
# SAFE INTERACTION WRAPPER
# =========================

async def safe_send(interaction, content):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content)
        else:
            await interaction.response.send_message(content)
    except:
        pass

# =========================
# DATA LAYER (ALPACA → YAHOO FALLBACK)
# =========================

async def fetch_alpaca(symbol):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        r = requests.get(
            url,
            headers=headers,
            params={"timeframe": "1Min", "limit": 120, "feed": "iex"},
            timeout=6
        )

        if r.status_code != 200:
            return None

        data = r.json().get("bars", [])
        if not data:
            return None

        return (
            [x["c"] for x in data],
            [x["h"] for x in data],
            [x["l"] for x in data],
            [x["v"] for x in data],
        )

    except:
        return None


async def fetch_yahoo(symbol):
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


async def get_data(symbol):
    # Alpaca first (market hours accuracy)
    if alpaca_enabled:
        data = await fetch_alpaca(symbol)
        if data:
            return data

    # fallback (after hours reliability)
    return await fetch_yahoo(symbol)

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

    rs = avg_g / avg_l if avg_l else 0
    rsi = 100 - (100 / (1 + rs)) if rs else 50

    macd = statistics.mean(c[-12:]) - statistics.mean(c[-26:]) if len(c) >= 26 else 0

    return vwap, rsi, macd


def levels(h, l):
    return min(l[-50:]), max(h[-50:])


def breakout(price, resistance):
    return price > resistance * 0.995


def score(c, h, l, v):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]
    s = 50

    s += 15 if price > vwap else -15
    s += 10 if rsi > 70 else -10 if rsi < 30 else 0
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
# COMMANDS (STABLE REGISTRATION)
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction: discord.Interaction):
    await safe_send(interaction,
        "Commands:\n"
        "/scan\n/scalp\n/breakout\n/besttrade\n/watch\n/mode"
    )


@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(interaction: discord.Interaction, mode: str):
    await safe_send(interaction, f"Mode set → {mode}")


@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(interaction: discord.Interaction):
    await interaction.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = await get_data(t)

        if not data:
            out.append(f"{t}: NO DATA")
            continue

        c, h, l, v = data
        s, sig, *_ = score(c, h, l, v)
        out.append(f"{t}: {sig} ({s}/100)")

    await safe_send(interaction, "\n".join(out))


@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    data = await get_data(symbol)

    if not data:
        return await safe_send(interaction, "No data available")

    c, h, l, v = data
    s, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    await safe_send(interaction,
        f"{symbol}\n{sig} ({s})\nVWAP {vwap:.2f}\nRSI {rsi:.1f}\nMACD {macd:.2f}"
    )


@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout_cmd(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer()

    data = await get_data(symbol)
    if not data:
        return await safe_send(interaction, "No data")

    c, h, l, v = data
    _, r = levels(h, l)

    msg = "🚀 BREAKOUT" if c[-1] > r * 0.995 else "📉 NO BREAKOUT"
    await safe_send(interaction, msg)


@tree.command(name="besttrade", guild=discord.Object(id=GUILD_ID))
async def besttrade(interaction: discord.Interaction):
    await interaction.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    best = ("NONE", 0)
    out = []

    for t in tickers:
        data = await get_data(t)
        if not data:
            continue

        c, h, l, v = data
        s, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({s})")

        if s > best[1]:
            best = (t, s)

    out.append(f"\nBEST: {best[0]} ({best[1]}/100)")
    await safe_send(interaction, "\n".join(out))


@tree.command(name="watch", guild=discord.Object(id=GUILD_ID))
async def watch(interaction: discord.Interaction, symbol: str):
    await safe_send(interaction, f"Watching {symbol}")


# =========================
# CRITICAL FIX: PROPER SYNC
# =========================

@client.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    # FULL CLEAN SYNC (prevents ghost commands)
    tree.clear_commands(guild=guild)

    await tree.sync(guild=guild)

    print("SYNC OK")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


# =========================
# RUN
# =========================

client.run(DISCORD_TOKEN)
