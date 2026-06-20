import os
import discord
from discord import app_commands
import requests
import statistics
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

headers = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET
} if alpaca_enabled else {}

# =========================
# BOT SETUP (FIXED PROPER WAY)
# =========================

intents = discord.Intents.default()
bot = discord.Bot(intents=intents)  # IMPORTANT FIX (NOT Client)
tree = bot.tree

user_modes = {}
watchlists = {}

# =========================
# DATA ENGINE (ALPACA + YAHOO FALLBACK)
# =========================

def get_bars_alpaca(symbol):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        r = requests.get(
            url,
            headers=headers,
            params={"timeframe": "1Min", "limit": 120, "feed": "iex"},
            timeout=8
        )

        if r.status_code != 200:
            return None

        bars = r.json().get("bars", [])

        if not bars:
            return None

        c, h, l, v = [], [], [], []

        for b in bars:
            c.append(b["c"])
            h.append(b["h"])
            l.append(b["l"])
            v.append(b["v"])

        return c, h, l, v

    except:
        return None


def get_bars_yahoo(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="5d", interval="1m")

        if df is None or df.empty:
            return None

        c = df["Close"].tolist()
        h = df["High"].tolist()
        l = df["Low"].tolist()
        v = df["Volume"].tolist()

        return c, h, l, v

    except:
        return None


def get_bars(symbol):
    data = get_bars_alpaca(symbol)
    if data:
        return data

    return get_bars_yahoo(symbol)

# =========================
# INDICATORS
# =========================

def indicators(c, h, l, v):
    tp_vol = sum(((h[i] + l[i] + c[i]) / 3) * v[i] for i in range(len(c)))
    vol_sum = sum(v)

    vwap = tp_vol / vol_sum if vol_sum else c[-1]

    gains, losses = [], []

    for i in range(1, len(c)):
        diff = c[i] - c[i - 1]
        gains.append(diff if diff > 0 else 0)
        losses.append(abs(diff) if diff < 0 else 0)

    avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else 0
    avg_loss = sum(losses[-14:]) / 14 if len(losses) >= 14 else 1

    rs = avg_gain / avg_loss if avg_loss else 100
    rsi = 100 - (100 / (1 + rs))

    ema12 = statistics.mean(c[-12:])
    ema26 = statistics.mean(c[-26:]) if len(c) >= 26 else ema12

    macd = ema12 - ema26

    return vwap, rsi, macd


def levels(h, l):
    return min(l[-50:]), max(h[-50:])


def is_breakout(price, resistance):
    return price > resistance * 0.995


def score(c, h, l, v):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]
    s = 50

    s += 15 if price > vwap else -15

    if rsi > 70:
        s += 10
    elif rsi < 30:
        s -= 10

    s += 15 if macd > 0 else -15

    if is_breakout(price, resistance):
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
        sig = "⏸ NO TRADE"

    return s, sig, vwap, rsi, macd, support, resistance

# =========================
# COMMANDS
# =========================

@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(ctx):
    await ctx.response.defer()

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = get_bars(t)
        if not data:
            out.append(f"{t}: NO DATA")
            continue

        c, h, l, v = data
        s, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({s})")

    await ctx.followup.send("\n".join(out))


@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(ctx, symbol: str):
    await ctx.response.defer()

    data = get_bars(symbol)

    if not data:
        return await ctx.followup.send("No data available")

    c, h, l, v = data
    s, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    await ctx.followup.send(
        f"{symbol}\n{sig} ({s})\nVWAP: {vwap:.2f}\nRSI: {rsi:.1f}\nMACD: {macd:.3f}"
    )


@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout(ctx, symbol: str):
    await ctx.response.defer()

    data = get_bars(symbol)

    if not data:
        return await ctx.followup.send("No data")

    c, h, l, v = data
    _, resistance = levels(h, l)

    msg = "🚀 BREAKOUT" if is_breakout(c[-1], resistance) else "📉 NO BREAKOUT"
    await ctx.followup.send(msg)


@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode(ctx, mode: str):
    user_modes[ctx.user.id] = mode
    await ctx.response.send_message(f"Mode set: {mode}")


@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(ctx):
    await ctx.response.send_message(
        "/scan /scalp /breakout /mode /watch"
    )

# =========================
# CLEAN SYNC FIX
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    tree.clear_commands(guild=guild)
    await tree.sync(guild=guild)

    print("Guild sync success V8")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
