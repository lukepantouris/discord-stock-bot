import os
import discord
from discord import app_commands
import requests
import statistics

# =========================
# ENV SAFE LOAD
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")
GUILD_ID = 1516963264486183053

BASE_URL = "https://data.alpaca.markets/v2"

headers = {}
if ALPACA_KEY and ALPACA_SECRET:
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }
else:
    print("WARNING: Alpaca keys missing → trading disabled")


# =========================
# DISCORD SETUP (NO DUPES FIXED)
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

user_modes = {}
watchlists = {}
alerts = {}


# =========================
# HELP COMMAND (KEEP)
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(i: discord.Interaction):
    msg = """
**📊 Stock Bot Commands**

/scan - market scanner  
/scalp <symbol> - 1m scalping signal  
/rate <symbol> - full analysis  
/compare <a> <b> - compare stocks  
/breakout <symbol> - breakout detection  
/besttrade - best setup scanner  
/mode <day/swing/invest> - trading style  
/watch <symbol> - add watchlist  
"""
    await i.response.send_message(msg)


# =========================
# SAFE ALPACA DATA FETCH (FIXED)
# =========================

def get_bars(symbol):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": "1Min",
            "limit": 120,
            "feed": "iex"
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            return None

        data = r.json()
        bars = data.get("bars", [])

        if not bars:
            return None

        closes = [b["c"] for b in bars if b.get("c")]
        highs = [b["h"] for b in bars if b.get("h")]
        lows = [b["l"] for b in bars if b.get("l")]
        vols = [b["v"] for b in bars if b.get("v")]

        if len(closes) < 20:
            return None

        return closes, highs, lows, vols

    except:
        return None


# =========================
# INDICATORS (VWAP RSI MACD)
# =========================

def indicators(closes, highs, lows, vols):
    # VWAP
    tp_vol = 0
    vol_sum = 0

    for i in range(len(closes)):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        tp_vol += tp * vols[i]
        vol_sum += vols[i]

    vwap = tp_vol / vol_sum if vol_sum else closes[-1]

    # RSI
    gains, losses = [], []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else 0
    avg_loss = sum(losses[-14:]) / 14 if len(losses) >= 14 else 1

    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = statistics.mean(closes[-12:])
    ema26 = statistics.mean(closes[-26:]) if len(closes) >= 26 else ema12

    macd = ema12 - ema26

    return vwap, rsi, macd


# =========================
# SUPPORT / RESISTANCE + BREAKOUT
# =========================

def levels(highs, lows):
    support = min(lows[-50:])
    resistance = max(highs[-50:])
    return support, resistance


def breakout(price, resistance):
    return price > resistance * 0.995


# =========================
# SCALPING ENGINE (CORE)
# =========================

def score_engine(c, h, l, v):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]

    score = 50

    # VWAP
    score += 15 if price > vwap else -15

    # RSI
    if rsi > 70:
        score += 10
    elif rsi < 30:
        score -= 10

    # MACD
    score += 15 if macd > 0 else -15

    # BREAKOUT
    if breakout(price, resistance):
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
async def mode(i: discord.Interaction, mode: str):
    user_modes[i.user.id] = mode
    await i.response.send_message(f"Mode set → {mode}")


# =========================
# SCAN COMMAND (FIXED NO EMPTY ERRORS)
# =========================

@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(i: discord.Interaction):
    await i.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = get_bars(t)

        if not data:
            out.append(f"{t}: NO DATA")
            continue

        c, h, l, v = data
        score, signal, *_ = score_engine(c, h, l, v)

        out.append(f"{t}: {signal} ({score}/100)")

    await i.followup.send("\n".join(out))


# =========================
# SCALP COMMAND (KEEP + FIX)
# =========================

@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data available")
        return

    c, h, l, v = data
    score, signal, vwap, rsi, macd, support, resistance = score_engine(c, h, l, v)

    msg = f"""
📊 {symbol}
{signal} ({score}/100)

VWAP: {vwap:.2f}
RSI: {rsi:.1f}
MACD: {macd:.3f}

Support: {support:.2f}
Resistance: {resistance:.2f}
"""

    await i.followup.send(msg)


# =========================
# BREAKOUT COMMAND (NEW BUT SAFE)
# =========================

@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout_cmd(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data")
        return

    c, h, l, v = data
    _, resistance = levels(h, l)

    price = c[-1]

    if breakout(price, resistance):
        msg = f"🚀 {symbol} BREAKING OUT"
    else:
        msg = f"📉 {symbol} NOT breaking resistance"

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
        score, signal, *_ = score_engine(c, h, l, v)

        out.append(f"{t}: {signal} ({score})")

        if score > best[1]:
            best = (t, score)

    out.append(f"\n🏆 BEST TRADE: {best[0]} ({best[1]}/100)")

    await i.followup.send("\n".join(out))


# =========================
# WATCHLIST (SIMPLE MEMORY)
# =========================

@tree.command(name="watch", guild=discord.Object(id=GUILD_ID))
async def watch(i: discord.Interaction, symbol: str):
    uid = i.user.id

    if uid not in watchlists:
        watchlists[uid] = []

    watchlists[uid].append(symbol.upper())

    await i.response.send_message(f"Added {symbol} to watchlist")


# =========================
# READY + SYNC FIXED
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    await tree.sync(guild=guild)
    print("Guild sync success")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# RUN BOT
# =========================

bot.run(DISCORD_TOKEN)
