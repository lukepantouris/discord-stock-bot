import os
import discord
from discord import app_commands
import requests
import statistics
import time

# =========================
# ENV SAFE LOAD
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

GUILD_ID = 1516963264486183053

BASE_URL = "https://data.alpaca.markets/v2"

headers = {}
alpaca_enabled = True

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

if not ALPACA_KEY or not ALPACA_SECRET:
    print("WARNING: Alpaca keys missing → trading disabled")
    alpaca_enabled = False
else:
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }


# =========================
# DISCORD BOT SETUP (FIXED SYNC)
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

user_modes = {}
watchlists = {}


# =========================
# HELP
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(i: discord.Interaction):
    await i.response.send_message(
        "**V7 Trading Bot Commands**\n"
        "/scan - market scanner\n"
        "/scalp <symbol> - scalping engine\n"
        "/rate <symbol> - full analysis\n"
        "/compare <a> <b> - compare stocks\n"
        "/breakout <symbol>\n"
        "/mode <day/swing/invest>\n"
        "/watch <symbol>\n"
    )


# =========================
# SAFE ALPACA FETCH (V7 FIX)
# =========================

def get_bars(symbol):
    if not alpaca_enabled:
        return None

    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": "1Min",
            "limit": 120,
            "feed": "iex"
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            print("ALPACA ERROR:", r.status_code, r.text)
            return None

        data = r.json()

        bars = data.get("bars", [])

        if not bars:
            return None

        closes = []
        highs = []
        lows = []
        vols = []

        for b in bars:
            if all(k in b for k in ["c", "h", "l", "v"]):
                closes.append(b["c"])
                highs.append(b["h"])
                lows.append(b["l"])
                vols.append(b["v"])

        if len(closes) < 20:
            return None

        return closes, highs, lows, vols

    except Exception as e:
        print("FETCH ERROR:", e)
        return None


# =========================
# INDICATORS (VWAP / RSI / MACD)
# =========================

def indicators(c, h, l, v):
    # VWAP
    tp_vol = 0
    vol_sum = 0

    for i in range(len(c)):
        tp = (h[i] + l[i] + c[i]) / 3
        tp_vol += tp * v[i]
        vol_sum += v[i]

    vwap = tp_vol / vol_sum if vol_sum else c[-1]

    # RSI
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

    rs = avg_gain / avg_loss if avg_loss else 100
    rsi = 100 - (100 / (1 + rs))

    # MACD (simple)
    ema12 = statistics.mean(c[-12:])
    ema26 = statistics.mean(c[-26:]) if len(c) >= 26 else ema12
    macd = ema12 - ema26

    return vwap, rsi, macd


# =========================
# SUPPORT / RESISTANCE
# =========================

def levels(h, l):
    support = min(l[-50:])
    resistance = max(h[-50:])
    return support, resistance


def is_breakout(price, resistance):
    return price > resistance * 0.995


# =========================
# SCORING ENGINE (CORE STRATEGY)
# =========================

def score(c, h, l, v):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]

    score = 50

    # VWAP trend
    score += 15 if price > vwap else -15

    # RSI logic
    if rsi > 70:
        score += 10
    elif rsi < 30:
        score -= 10

    # MACD
    score += 15 if macd > 0 else -15

    # breakout
    if is_breakout(price, resistance):
        score += 20

    score = max(0, min(100, score))

    if score >= 80:
        signal = "🔥 STRONG BUY"
    elif score >= 65:
        signal = "⚡ BUY SETUP"
    elif score <= 25:
        signal = "❄ STRONG SELL"
    elif score <= 40:
        signal = "⚡ SELL SETUP"
    else:
        signal = "⏸ NO TRADE"

    return score, signal, vwap, rsi, macd, support, resistance


# =========================
# MODE SYSTEM (KEEP FEATURE)
# =========================

@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(i: discord.Interaction, mode: str):
    user_modes[i.user.id] = mode
    await i.response.send_message(f"Mode set → {mode}")


# =========================
# SCAN (FIXED NO EMPTY MESSAGES)
# =========================

@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(i: discord.Interaction):
    await i.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

    out = []

    for t in tickers:
        data = get_bars(t)

        if not data:
            out.append(f"{t}: NO DATA (market or feed)")
            continue

        c, h, l, v = data
        sc, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({sc}/100)")

    await i.followup.send("\n".join(out))


# =========================
# SCALP ENGINE
# =========================

@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No market data available (Alpaca feed empty or delayed)")
        return

    c, h, l, v = data
    sc, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    msg = f"""
📊 {symbol}
{sig} ({sc}/100)

VWAP: {vwap:.2f}
RSI: {rsi:.1f}
MACD: {macd:.3f}

Support: {support:.2f}
Resistance: {resistance:.2f}
"""

    await i.followup.send(msg)


# =========================
# BREAKOUT
# =========================

@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data")
        return

    c, h, l, v = data
    _, resistance = levels(h, l)

    price = c[-1]

    if is_breakout(price, resistance):
        msg = f"🚀 {symbol} BREAKOUT DETECTED"
    else:
        msg = f"📉 {symbol} below resistance"

    await i.followup.send(msg)


# =========================
# BEST TRADE SCANNER
# =========================

@tree.command(name="besttrade", guild=discord.Object(id=GUILD_ID))
async def besttrade(i: discord.Interaction):
    await i.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

    best = ("NONE", 0)
    out = []

    for t in tickers:
        data = get_bars(t)
        if not data:
            continue

        c, h, l, v = data
        sc, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({sc})")

        if sc > best[1]:
            best = (t, sc)

    out.append(f"\n🏆 BEST: {best[0]} ({best[1]}/100)")

    await i.followup.send("\n".join(out))


# =========================
# WATCHLIST
# =========================

@tree.command(name="watch", guild=discord.Object(id=GUILD_ID))
async def watch(i: discord.Interaction, symbol: str):
    uid = i.user.id

    if uid not in watchlists:
        watchlists[uid] = []

    watchlists[uid].append(symbol.upper())

    await i.response.send_message(f"Watching {symbol}")


# =========================
# SYNC FIX (CRITICAL)
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    tree.clear_commands(guild=guild)
    tree.copy_global_to(guild=guild)

    await tree.sync(guild=guild)

    print("Guild sync success (V7)")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
