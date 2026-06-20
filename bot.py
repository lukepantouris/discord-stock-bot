import os
import discord
from discord import app_commands
import requests
import statistics

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
    "APCA-API-KEY-ID": ALPACA_KEY or "",
    "APCA-API-SECRET-KEY": ALPACA_SECRET or ""
}

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")


# =========================
# BOT SETUP (FIXED)
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

user_modes = {}
watchlists = {}


# =========================
# SAFE DATA FETCH (NO CRASH)
# =========================

def get_bars(symbol):
    """
    SAFE Alpaca fetch
    NEVER crashes bot even if API fails
    """

    if not alpaca_enabled:
        return None

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

        data = r.json()
        bars = data.get("bars", [])

        if not bars:
            return None

        c, h, l, v = [], [], [], []

        for b in bars:
            if all(k in b for k in ["c", "h", "l", "v"]):
                c.append(b["c"])
                h.append(b["h"])
                l.append(b["l"])
                v.append(b["v"])

        if len(c) < 20:
            return None

        return c, h, l, v

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

    gains, losses = [], []

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
# SUPPORT/RESISTANCE
# =========================

def levels(h, l):
    return min(l[-50:]), max(h[-50:])


def is_breakout(price, resistance):
    return price > resistance * 0.995


# =========================
# SCORING ENGINE
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
# COMMANDS (FIXED SYNC ISSUE)
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(i: discord.Interaction):
    await i.response.send_message(
        "**Trading Bot Commands**\n"
        "/scan\n"
        "/scalp <symbol>\n"
        "/breakout <symbol>\n"
        "/mode <day/swing/invest>\n"
        "/watch <symbol>\n"
    )


@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(i: discord.Interaction, mode: str):
    user_modes[i.user.id] = mode
    await i.response.send_message(f"Mode set → {mode}")


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
        sc, sig, *_ = score(c, h, l, v)

        out.append(f"{t}: {sig} ({sc}/100)")

    await i.followup.send("\n".join(out))


@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No market data available")
        return

    c, h, l, v = data
    sc, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    await i.followup.send(
        f"{symbol}\n{sig} ({sc})\nVWAP {vwap:.2f}\nRSI {rsi:.1f}\nMACD {macd:.2f}"
    )


@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data available")
        return

    c, h, l, v = data
    _, resistance = levels(h, l)

    price = c[-1]

    msg = "🚀 BREAKOUT" if is_breakout(price, resistance) else "📉 NO BREAKOUT"

    await i.followup.send(msg)


@tree.command(name="watch", guild=discord.Object(id=GUILD_ID))
async def watch(i: discord.Interaction, symbol: str):
    uid = i.user.id

    if uid not in watchlists:
        watchlists[uid] = []

    watchlists[uid].append(symbol.upper())

    await i.response.send_message(f"Watching {symbol}")


# =========================
# CRITICAL FIX: SYNC SYSTEM
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    tree.clear_commands(guild=guild)
    await tree.sync(guild=guild)

    print("Guild sync success")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
