import os
import discord
from discord import app_commands
import requests
import statistics
import yfinance as yf

# =========================
# CONFIG
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1516963264486183053

ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

BASE_URL = "https://data.alpaca.markets/v2"

alpaca_enabled = bool(ALPACA_KEY and ALPACA_SECRET)

headers = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET
} if alpaca_enabled else {}

# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

user_modes = {}
watchlists = {}

# =========================
# SAFE MESSAGE WRAPPER
# =========================

async def safe(interaction, func):
    try:
        await func()
    except Exception as e:
        try:
            await interaction.followup.send(f"⚠️ Error: {e}")
        except:
            pass

# =========================
# HELP
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(i: discord.Interaction):
    await i.response.send_message(
        "**V8 Trading Bot Commands**\n\n"
        "/scan\n"
        "/scalp <symbol>\n"
        "/rate <symbol>\n"
        "/compare <a> <b>\n"
        "/breakout <symbol>\n"
        "/mode <day/swing/invest>\n"
        "/watch <symbol>\n"
        "/besttrade\n"
    )

# =========================
# DATA ENGINE (ALPACA + YAHOO FALLBACK)
# =========================

def alpaca_data(symbol):
    try:
        if not alpaca_enabled:
            return None

        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": "1Min",
            "limit": 120,
            "feed": "iex"
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            return None

        bars = r.json().get("bars", [])

        if not bars:
            return None

        return clean(bars)

    except:
        return None


def yahoo_data(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="1m", progress=False)

        if df is None or len(df) < 20:
            return None

        c = df["Close"].tolist()
        h = df["High"].tolist()
        l = df["Low"].tolist()
        v = df["Volume"].tolist()

        return c, h, l, v

    except:
        return None


def get_bars(symbol):
    data = alpaca_data(symbol)

    if data:
        return data

    return yahoo_data(symbol)


def clean(bars):
    c, h, l, v = [], [], [], []

    for b in bars:
        if "c" in b and "h" in b and "l" in b and "v" in b:
            c.append(b["c"])
            h.append(b["h"])
            l.append(b["l"])
            v.append(b["v"])

    if len(c) < 20:
        return None

    return c, h, l, v

# =========================
# INDICATORS
# =========================

def indicators(c, h, l, v):

    tp_vol = sum(((h[i]+l[i]+c[i])/3)*v[i] for i in range(len(c)))
    vol_sum = sum(v)

    vwap = tp_vol / vol_sum if vol_sum else c[-1]

    gains = []
    losses = []

    for i in range(1, len(c)):
        diff = c[i] - c[i-1]
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
# SUPPORT / RESISTANCE
# =========================

def levels(h, l):
    return min(l[-50:]), max(h[-50:])

def breakout(price, resistance):
    return price > resistance * 0.995

# =========================
# MODE SYSTEM
# =========================

@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(i: discord.Interaction, mode: str):
    user_modes[i.user.id] = mode
    await i.response.send_message(f"Mode set → {mode}")

# =========================
# CORE SCORE ENGINE
# =========================

def score(c, h, l, v):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]

    score = 50

    score += 15 if price > vwap else -15

    if rsi > 70:
        score += 10
    elif rsi < 30:
        score -= 10

    score += 15 if macd > 0 else -15

    if breakout(price, resistance):
        score += 20

    score = max(0, min(100, score))

    if score >= 80:
        sig = "🔥 STRONG BUY"
    elif score >= 65:
        sig = "⚡ BUY SETUP"
    elif score <= 25:
        sig = "❄ STRONG SELL"
    elif score <= 40:
        sig = "⚡ SELL SETUP"
    else:
        sig = "⏸ NO TRADE"

    return score, sig, vwap, rsi, macd, support, resistance

# =========================
# SCAN
# =========================

@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(i: discord.Interaction):
    await i.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

    out = []

    for t in tickers:
        data = get_bars(t)

        if not data:
            out.append(f"{t}: NO DATA (Alpaca + Yahoo failed)")
            continue

        c, h, l, v = data
        sc, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({sc}/100)")

    await i.followup.send("\n".join(out))

# =========================
# SCALP
# =========================

@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data available")
        return

    c, h, l, v = data
    sc, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    await i.followup.send(
        f"📊 {symbol}\n{sig} ({sc}/100)\n"
        f"VWAP: {vwap:.2f}\nRSI: {rsi:.1f}\nMACD: {macd:.3f}\n"
        f"Support: {support:.2f}\nResistance: {resistance:.2f}"
    )

# =========================
# BREAKOUT
# =========================

@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout_cmd(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data")
        return

    c, h, l, v = data
    _, r = levels(h, l)

    msg = f"🚀 {symbol} BREAKOUT" if breakout(c[-1], r) else f"📉 {symbol} not breaking"

    await i.followup.send(msg)

# =========================
# BEST TRADE
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
# SYNC FIX (THIS IS WHY YOUR COMMANDS BROKE BEFORE)
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    tree.clear_commands(guild=guild)
    await tree.sync(guild=guild)

    print("Guild sync success (V8)")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
