import os
import discord
from discord import app_commands
import requests

# =========================
# KEYS
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

if not ALPACA_KEY or not ALPACA_SECRET:
    print("WARNING: Alpaca keys missing → trading disabled")

BASE_URL = "https://data.alpaca.markets/v2"

headers = {
    "APCA-API-KEY-ID": ALPACA_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET
}


# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# =========================
# HELP COMMAND
# =========================

@tree.command(name="help")
async def help_cmd(i: discord.Interaction):
    msg = (
        "**Commands**\n"
        "/scan - scans stocks\n"
        "/movers - top movers\n"
        "/rate - analyze stock\n"
    )
    await i.response.send_message(msg)


# =========================
# DATA FETCHER (FIXED)
# =========================

def get_data(symbol, timeframe="1Min"):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        params = {
            "timeframe": timeframe,
            "limit": 100,
            "feed": "iex",
            "adjustment": "raw"
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            return fallback(symbol)

        data = r.json()
        bars = data.get("bars", [])

        if not bars:
            return fallback(symbol)

        return clean(bars)

    except:
        return fallback(symbol)


def fallback(symbol):
    try:
        url = f"{BASE_URL}/stocks/{symbol}/bars"

        for tf in ["5Min", "1Day"]:
            params = {
                "timeframe": tf,
                "limit": 100,
                "feed": "iex",
                "adjustment": "raw"
            }

            r = requests.get(url, headers=headers, params=params, timeout=10)

            if r.status_code == 200:
                data = r.json()
                bars = data.get("bars", [])

                if bars:
                    return clean(bars)

        return None

    except:
        return None


def clean(bars):
    close, high, low, volume = [], [], [], []

    for b in bars:
        if None in (b.get("c"), b.get("h"), b.get("l"), b.get("v")):
            continue

        close.append(b["c"])
        high.append(b["h"])
        low.append(b["l"])
        volume.append(b["v"])

    if len(close) < 5:
        return None

    return close, high, low, volume


# =========================
# SCAN COMMAND (FIXED NO EMPTY MESSAGE)
# =========================

@tree.command(name="scan")
async def scan(i: discord.Interaction):
    await i.response.defer(thinking=True)

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = get_data(t)

        if not data:
            continue

        close, high, low, vol = data

        change = ((close[-1] - close[0]) / close[0]) * 100

        label = "STRONG" if abs(change) > 2 else "WEAK"

        out.append(f"{t}: {label} ({change:.2f}%)")

    if not out:
        out = ["No market data available right now"]

    await i.followup.send("\n".join(out))


# =========================
# ON READY
# =========================

@bot.event
async def on_ready():
    await tree.sync()
    print("Slash commands synced")


# =========================
# RUN BOT
# =========================

bot.run(DISCORD_TOKEN)
