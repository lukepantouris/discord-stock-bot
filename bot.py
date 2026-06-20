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

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

alpaca_enabled = bool(ALPACA_KEY and ALPACA_SECRET)

headers = {
    "APCA-API-KEY-ID": ALPACA_KEY or "",
    "APCA-API-SECRET-KEY": ALPACA_SECRET or ""
}

# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

user_modes = {}
watchlists = {}

guild_obj = discord.Object(id=GUILD_ID)


# =========================
# SAFE ALPACA FETCH
# =========================

def get_bars(symbol):
    if not alpaca_enabled:
        return None

    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": "1Min",
            "limit": 120
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            print("ALPACA ERROR:", r.status_code, r.text)
            return None

        data = r.json()
        bars = data.get("bars", [])

        if not bars:
            return None

        closes, highs, lows, vols = [], [], [], []

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
# INDICATORS
# =========================

def indicators(c, h, l, v):
    tp_sum = 0
    vol_sum = 0

    for i in range(len(c)):
        tp = (h[i] + l[i] + c[i]) / 3
        tp_sum += tp * v[i]
        vol_sum += v[i]

    vwap = tp_sum / vol_sum if vol_sum else c[-1]

    gains, losses = [], []

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

    if price > vwap:
        s += 15
    else:
        s -= 15

    if rsi > 70:
        s += 10
    elif rsi < 30:
        s -= 10

    s += 15 if macd > 0 else -15

    if is_breakout(price, resistance):
        s += 20

    s = max(0, min(100, s))

    if s >= 80:
        signal = "🔥 STRONG BUY"
    elif s >= 65:
        signal = "⚡ BUY SETUP"
    elif s <= 25:
        signal = "❄ STRONG SELL"
    elif s <= 40:
        signal = "⚡ SELL SETUP"
    else:
        signal = "⏸ NO TRADE"

    return s, signal, vwap, rsi, macd, support, resistance


# =========================
# HELP
# =========================

@tree.command(name="help", guild=guild_obj)
async def help_cmd(i: discord.Interaction):
    await i.response.send_message(
        "/scan\n/scalp <symbol>\n/breakout <symbol>\n/besttrade\n/mode <type>\n/watch <symbol>"
    )


# =========================
# MODE
# =========================

@tree.command(name="mode", guild=guild_obj)
async def mode_cmd(i: discord.Interaction, mode: str):
    user_modes[i.user.id] = mode
    await i.response.send_message(f"Mode set: {mode}")


# =========================
# SCAN
# =========================

@tree.command(name="scan", guild=guild_obj)
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


# =========================
# SCALP
# =========================

@tree.command(name="scalp", guild=guild_obj)
async def scalp(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data available")
        return

    c, h, l, v = data
    sc, sig, vwap, rsi, macd, support, resistance = score(c, h, l, v)

    await i.followup.send(
        f"{symbol}\n{sig} ({sc}/100)\nVWAP {vwap:.2f}\nRSI {rsi:.1f}\nMACD {macd:.3f}"
    )


# =========================
# BREAKOUT
# =========================

@tree.command(name="breakout", guild=guild_obj)
async def breakout(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data")
        return

    c, h, l, v = data
    _, r = levels(h, l)

    if c[-1] > r:
        await i.followup.send(f"🚀 {symbol} breakout")
    else:
        await i.followup.send(f"📉 {symbol} not breaking")


# =========================
# BEST TRADE
# =========================

@tree.command(name="besttrade", guild=guild_obj)
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

    out.append(f"\nBEST: {best[0]} ({best[1]})")

    await i.followup.send("\n".join(out))


# =========================
# WATCH
# =========================

@tree.command(name="watch", guild=guild_obj)
async def watch(i: discord.Interaction, symbol: str):
    uid = i.user.id
    watchlists.setdefault(uid, []).append(symbol.upper())
    await i.response.send_message(f"Watching {symbol}")


# =========================
# FIXED SYNC (NO MORE CRASH)
# =========================

@bot.event
async def setup_hook():
    await tree.sync(guild=guild_obj)
    print("Guild sync success")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# RUN (FIXED SYNTAX ERROR)
# =========================

bot.run(DISCORD_TOKEN)
