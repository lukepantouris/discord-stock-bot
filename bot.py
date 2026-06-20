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

GUILD_ID = 0  # 🔴 PUT YOUR SERVER ID

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
# MEMORY SYSTEM (NEW)
# =========================

user_mode = {}  # user_id -> mode


def get_mode(user_id):
    return user_mode.get(user_id, "invest")


def set_mode(user_id, mode):
    user_mode[user_id] = mode


# =========================
# DISCORD SETUP
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# =========================
# DATA FETCH
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
    last = close[-1]

    avg = sum(vol[:-1]) / len(vol[:-1])
    spike = vol[-1] > avg * 1.5

    return last > resistance and spike


# =========================
# HELP
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(i: discord.Interaction):
    await i.response.send_message(
        "**📊 V4 BOT COMMANDS**\n"
        "/scan\n"
        "/rate <symbol>\n"
        "/breakout\n"
        "/chart <symbol>\n"
        "/compare <A> <B>\n"
        "/mode <day/swing/invest>\n"
    )


# =========================
# MODE COMMAND (NEW)
# =========================

@tree.command(name="mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(i: discord.Interaction, mode: str):
    mode = mode.lower()

    if mode not in ["day", "swing", "invest"]:
        await i.response.send_message("Modes: day / swing / invest")
        return

    set_mode(i.user.id, mode)
    await i.response.send_message(f"Mode set to: {mode.upper()}")


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

        if mode == "day":
            label = "⚡ DAY TRADE"
        elif mode == "swing":
            label = "📈 SWING"
        else:
            label = "💼 INVEST"

        out.append(f"{t}: {label} ({change:.2f}%)")

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
            out.append(f"— {t}: no setup")

    await i.followup.send("\n".join(out))


# =========================
# RATE
# =========================

@tree.command(name="rate", guild=discord.Object(id=GUILD_ID))
async def rate_cmd(i: discord.Interaction, symbol: str):
    await i.response.send_message(f"Analyzing {symbol}...")

    data = get_data(symbol)

    if not data:
        await i.followup.send("No data")
        return

    c, h, v = data
    change = ((c[-1] - c[0]) / c[0]) * 100

    if change > 2:
        rating = "BULLISH"
    elif change < -2:
        rating = "BEARISH"
    else:
        rating = "NEUTRAL"

    await i.followup.send(f"{symbol}: {rating} ({change:.2f}%)")


# =========================
# COMPARE (NEW)
# =========================

@tree.command(name="compare", guild=discord.Object(id=GUILD_ID))
async def compare_cmd(i: discord.Interaction, a: str, b: str):
    await i.response.send_message("Comparing...")

    da = get_data(a)
    db = get_data(b)

    if not da or not db:
        await i.followup.send("No data for comparison")
        return

    ca = da[0]
    cb = db[0]

    pa = ((ca[-1] - ca[0]) / ca[0]) * 100
    pb = ((cb[-1] - cb[0]) / cb[0]) * 100

    winner = a if pa > pb else b

    await i.followup.send(f"{a}: {pa:.2f}%\n{b}: {pb:.2f}%\nWINNER: {winner}")


# =========================
# READY (FIXED SYNC)
# =========================

@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)

    tree.clear_commands(guild=guild)
    tree.copy_global_to(guild=guild)

    await tree.sync(guild=guild)
    print("Commands synced (V4)")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
