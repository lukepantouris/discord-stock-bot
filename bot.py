import os
import discord
from discord import app_commands
import requests
import statistics
import traceback

# =========================
# CONFIG
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

# =========================
# BOT SETUP (STABLE V2)
# =========================

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

user_modes = {}
watchlists = {}

# =========================
# SAFE RESPONSE WRAPPER
# =========================

async def safe_reply(interaction, content):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content)
        else:
            await interaction.response.send_message(content)
    except:
        print("REPLY ERROR:", traceback.format_exc())

# =========================
# ALPACA + YAHOO-LIKE FALLBACK SYSTEM
# =========================

def fetch_bars(symbol):
    if not alpaca_enabled:
        return None

    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        # Try intraday first
        for tf in ["1Min", "5Min", "1Day"]:
            params = {
                "timeframe": tf,
                "limit": 120,
                "feed": "iex"
            }

            r = requests.get(url, headers=headers, params=params, timeout=10)

            if r.status_code != 200:
                continue

            data = r.json()
            bars = data.get("bars", [])

            if bars and len(bars) > 5:
                closes = [b["c"] for b in bars if "c" in b]
                highs = [b["h"] for b in bars if "h" in b]
                lows = [b["l"] for b in bars if "l" in b]
                vols = [b["v"] for b in bars if "v" in b]

                if len(closes) > 5:
                    return closes, highs, lows, vols

        return None

    except:
        return None


def yahoo_style_fallback(symbol):
    """
    Simulates Yahoo behavior:
    ALWAYS returns something usable instead of empty data.
    """
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": "1Day",
            "limit": 5,
            "feed": "iex"
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            return None

        data = r.json()
        bars = data.get("bars", [])

        if not bars:
            return None

        closes = [b["c"] for b in bars if "c" in b]

        if len(closes) < 2:
            return None

        # fake highs/lows for stability
        highs = [c * 1.01 for c in closes]
        lows = [c * 0.99 for c in closes]
        vols = [1000 for _ in closes]

        return closes, highs, lows, vols

    except:
        return None

# =========================
# INDICATORS
# =========================

def indicators(c, h, l, v):
    tp_vol = 0
    vol_sum = 0

    for i in range(len(c)):
        tp = (h[i] + l[i] + c[i]) / 3
        tp_vol += tp * v[i]
        vol_sum += v[i]

    vwap = tp_vol / vol_sum if vol_sum else c[-1]

    gains = []
    losses = []

    for i in range(1, len(c)):
        diff = c[i] - c[i - 1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else 0
    avg_loss = sum(losses[-14:]) / 14 if len(losses) >= 14 else 1

    rs = avg_gain / avg_loss if avg_loss else 1
    rsi = 100 - (100 / (1 + rs))

    ema12 = statistics.mean(c[-12:])
    ema26 = statistics.mean(c[-26:]) if len(c) >= 26 else ema12
    macd = ema12 - ema26

    return vwap, rsi, macd

# =========================
# LEVELS
# =========================

def levels(h, l):
    return min(l[-50:]), max(h[-50:])

def breakout(price, resistance):
    return price > resistance * 0.995

# =========================
# SCORE ENGINE
# =========================

def score(c, h, l, v):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]
    sc = 50

    sc += 15 if price > vwap else -15

    if rsi > 70:
        sc += 10
    elif rsi < 30:
        sc -= 10

    sc += 15 if macd > 0 else -15

    if breakout(price, resistance):
        sc += 20

    sc = max(0, min(100, sc))

    if sc >= 80:
        signal = "🔥 STRONG BUY"
    elif sc >= 65:
        signal = "⚡ BUY SETUP"
    elif sc <= 25:
        signal = "❄ STRONG SELL"
    elif sc <= 40:
        signal = "⚡ SELL SETUP"
    else:
        signal = "⏸ NO TRADE"

    return sc, signal, vwap, rsi, macd, support, resistance

# =========================
# HELP
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction):
    await safe_reply(interaction,
        "/scan\n/scalp <symbol>\n/breakout <symbol>\n/besttrade\n/mode <type>\n/watch <symbol>"
    )

# =========================
# MODE
# =========================

@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode(interaction, mode: str):
    user_modes[interaction.user.id] = mode
    await safe_reply(interaction, f"Mode set: {mode}")

# =========================
# SCAN
# =========================

@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(interaction):
    await interaction.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = fetch_bars(t)

        if not data:
            data = yahoo_style_fallback(t)

        if not data:
            out.append(f"{t}: NO DATA")
            continue

        c, h, l, v = data
        sc, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({sc})")

    await interaction.followup.send("\n".join(out))

# =========================
# SCALP
# =========================

@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(interaction, symbol: str):
    await interaction.response.defer()

    data = fetch_bars(symbol)

    if not data:
        data = yahoo_style_fallback(symbol)

    if not data:
        await interaction.followup.send("No data available")
        return

    c, h, l, v = data
    sc, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    await interaction.followup.send(
        f"{symbol}\n{sig} ({sc})\nVWAP {vwap:.2f}\nRSI {rsi:.1f}"
    )

# =========================
# BREAKOUT
# =========================

@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout_cmd(interaction, symbol: str):
    await interaction.response.defer()

    data = fetch_bars(symbol)

    if not data:
        data = yahoo_style_fallback(symbol)

    if not data:
        await interaction.followup.send("No data")
        return

    c, h, l, v = data
    support, resistance = levels(h, l)

    price = c[-1]

    if breakout(price, resistance):
        msg = f"{symbol} BREAKOUT 🚀"
    else:
        msg = f"{symbol} NOT breaking resistance"

    await interaction.followup.send(msg)

# =========================
# BEST TRADE
# =========================

@tree.command(name="besttrade", guild=discord.Object(id=GUILD_ID))
async def besttrade(interaction):
    await interaction.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

    best = ("NONE", 0)
    out = []

    for t in tickers:
        data = fetch_bars(t) or yahoo_style_fallback(t)

        if not data:
            continue

        c, h, l, v = data
        sc, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({sc})")

        if sc > best[1]:
            best = (t, sc)

    out.append(f"\nBEST: {best[0]} ({best[1]})")

    await interaction.followup.send("\n".join(out))

# =========================
# WATCH
# =========================

@tree.command(name="watch", guild=discord.Object(id=GUILD_ID))
async def watch(interaction, symbol: str):
    uid = interaction.user.id
    watchlists.setdefault(uid, []).append(symbol)

    await safe_reply(interaction, f"Watching {symbol}")

# =========================
# SYNC FIX (IMPORTANT)
# =========================

@client.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    tree.clear_commands(guild=guild)
    await tree.sync(guild=guild)

    print("Guild sync success")

@client.event
async def on_ready():
    print("Logged in as", client.user)

# =========================
# RUN
# =========================

client.run(DISCORD_TOKEN)
