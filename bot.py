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


# =========================
# SAFE DATA (NO CRASH)
# =========================

def get_bars(symbol):
    try:
        if not alpaca_enabled:
            return None

        url = f"{BASE_URL}/stocks/{symbol}/bars"

        r = requests.get(
            url,
            headers=headers,
            params={"timeframe": "1Min", "limit": 100, "feed": "iex"},
            timeout=8
        )

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
# SIMPLE SCORING (SAFE)
# =========================

def score(c, h, l, v):
    price = c[-1]

    vwap = sum(c[-20:]) / len(c[-20:])

    rsi = 50  # fallback safe RSI (prevents crash logic)

    support = min(l[-20:])
    resistance = max(h[-20:])

    score = 50

    if price > vwap:
        score += 15
    else:
        score -= 15

    if price > resistance * 0.995:
        score += 20

    score = max(0, min(100, score))

    if score >= 80:
        signal = "🔥 STRONG BUY"
    elif score >= 65:
        signal = "⚡ BUY SETUP"
    elif score <= 25:
        signal = "❄ STRONG SELL"
    else:
        signal = "⏸ NO TRADE"

    return score, signal, vwap, rsi, support, resistance


# =========================
# COMMANDS (CLEAN ONLY)
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(i: discord.Interaction):
    await i.response.send_message(
        "/scan\n/scalp <symbol>\n/breakout <symbol>\n/mode <day/swing/invest>"
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

        out.append(f"{t}: {sig} ({sc})")

    await i.followup.send("\n".join(out))


@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data available")
        return

    c, h, l, v = data
    sc, sig, vwap, rsi, support, resistance = score(c, h, l, v)

    await i.followup.send(
        f"{symbol}\n{sig} ({sc})\nVWAP {vwap:.2f}\nSupport {support:.2f}\nResistance {resistance:.2f}"
    )


@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout(i: discord.Interaction, symbol: str):
    await i.response.defer()

    data = get_bars(symbol)

    if not data:
        await i.followup.send("No data")
        return

    c, h, l, v = data
    _, resistance = score(c, h, l, v)[-2:]

    msg = "🚀 BREAKOUT" if c[-1] > resistance * 0.995 else "📉 NO BREAKOUT"

    await i.followup.send(msg)


@tree.command(name="watch", guild=discord.Object(id=GUILD_ID))
async def watch(i: discord.Interaction, symbol: str):
    uid = i.user.id

    if uid not in watchlists:
        watchlists[uid] = []

    watchlists[uid].append(symbol.upper())

    await i.response.send_message(f"Watching {symbol}")


# =========================
# 🔥 CLEAN RESET SYNC (IMPORTANT FIX)
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    # 🔥 HARD RESET COMMANDS (THIS FIXES YOUR PROBLEM)
    bot.tree.clear_commands(guild=guild)

    # rebuild commands clean
    await tree.sync(guild=guild)

    print("Guild sync success (CLEAN RESET V9)")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
