import os
import discord
from discord import app_commands
import requests

# =========================
# ENV
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

GUILD_ID = 1516963264486183053  # ✅ YOUR SERVER ID

BASE_URL = "https://data.alpaca.markets/v2"

headers = {}
if ALPACA_KEY and ALPACA_SECRET:
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }
else:
    print("WARNING: Alpaca disabled")


# =========================
# MEMORY SYSTEM
# =========================

user_mode = {}

def get_mode(uid):
    return user_mode.get(uid, "invest")

def set_mode(uid, mode):
    user_mode[uid] = mode


# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# =========================
# SAFE DATA FETCH
# =========================

def get_data(symbol):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        for tf in ["1Min", "5Min", "1Day"]:
            params = {
                "timeframe": tf,
                "limit": 100,
                "feed": "iex",
                "adjustment": "raw"
            }

            r = requests.get(url, headers=headers, params=params, timeout=10)

            if r.status_code != 200:
                continue

            data = r.json()
            bars = data.get("bars", [])

            if not bars:
                continue

            close = [b["c"] for b in bars]
            high = [b["h"] for b in bars]
            vol = [b["v"] for b in bars]

            if len(close) > 10:
                return close, high, vol

        return None

    except:
        return None


# =========================
# BREAKOUT LOGIC
# =========================

def breakout(high, close, vol):
    resistance = max(high[:-5])
    return close[-1] > resistance and vol[-1] > sum(vol[:-1]) / len(vol[:-1]) * 1.5


# =========================
# HELP
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(i: discord.Interaction):
    await i.response.send_message(
        "/scan\n/breakout\n/rate\n/compare\n/mode"
    )


# =========================
# MODE
# =========================

@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(i: discord.Interaction, mode: str):
    if mode not in ["day", "swing", "invest"]:
        await i.response.send_message("Use: day / swing / invest")
        return

    set_mode(i.user.id, mode)
    await i.response.send_message(f"Mode set: {mode}")


# =========================
# SCAN
# =========================

@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan(i: discord.Interaction):
    await i.response.send_message("Scanning...")

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = get_data(t)

        if not data:
            out.append(f"{t}: NO DATA")
            continue

        c, h, v = data
        change = ((c[-1] - c[0]) / c[0]) * 100

        mode = get_mode(i.user.id)
        tag = {"day":"⚡ DAY","swing":"📈 SWING","invest":"💼 INVEST"}[mode]

        out.append(f"{t}: {tag} ({change:.2f}%)")

    await i.followup.send("\n".join(out))


# =========================
# BREAKOUT
# =========================

@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout_cmd(i: discord.Interaction):
    await i.response.send_message("Checking breakouts...")

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = get_data(t)

        if not data:
            continue

        c, h, v = data

        if breakout(h, c, v):
            out.append(f"🚀 {t}: BREAKOUT")
        else:
            out.append(f"{t}: no setup")

    await i.followup.send("\n".join(out))


# =========================
# RATE
# =========================

@tree.command(name="rate", guild=discord.Object(id=GUILD_ID))
async def rate_cmd(i: discord.Interaction, symbol: str):
    await i.response.send_message("Analyzing...")

    data = get_data(symbol)

    if not data:
        await i.followup.send("No data")
        return

    c, h, v = data
    change = ((c[-1] - c[0]) / c[0]) * 100

    rating = "BULLISH" if change > 2 else "BEARISH" if change < -2 else "NEUTRAL"

    await i.followup.send(f"{symbol}: {rating} ({change:.2f}%)")


# =========================
# COMPARE
# =========================

@tree.command(name="compare", guild=discord.Object(id=GUILD_ID))
async def compare_cmd(i: discord.Interaction, a: str, b: str):
    await i.response.send_message("Comparing...")

    da = get_data(a)
    db = get_data(b)

    if not da or not db:
        await i.followup.send("No data")
        return

    pa = ((da[0][-1] - da[0][0]) / da[0][0]) * 100
    pb = ((db[0][-1] - db[0][0]) / db[0][0]) * 100

    await i.followup.send(f"{a}: {pa:.2f}%\n{b}: {pb:.2f}%")


# =========================
# SAFE SYNC (FIXED)
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    try:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print("Guild sync success")

    except discord.Forbidden:
        print("Guild sync failed → falling back to global sync")
        await tree.sync()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
