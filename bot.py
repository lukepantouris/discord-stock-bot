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

BASE_URL = "https://data.alpaca.markets/v2"

headers = {}
if ALPACA_KEY and ALPACA_SECRET:
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
    await i.response.send_message(
        "**📊 Commands**\n"
        "/scan - market scan\n"
        "/movers - top movers (basic)\n"
        "/breakout - breakout detection\n"
        "/rate - stock strength rating\n"
    )


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

            close = [b["c"] for b in bars if b.get("c") is not None]
            high = [b["h"] for b in bars if b.get("h") is not None]
            volume = [b["v"] for b in bars if b.get("v") is not None]

            if len(close) >= 10:
                return close, high, volume

        return None

    except:
        return None


# =========================
# BREAKOUT ENGINE (NEW)
# =========================

def detect_breakout(highs, closes, volumes):
    try:
        resistance = max(highs[:-5])  # previous resistance zone
        last_close = closes[-1]

        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
        last_vol = volumes[-1]

        volume_spike = last_vol > avg_vol * 1.5

        breakout = last_close > resistance and volume_spike

        return {
            "breakout": breakout,
            "resistance": resistance,
            "volume_spike": volume_spike
        }

    except:
        return {
            "breakout": False,
            "resistance": 0,
            "volume_spike": False
        }


# =========================
# SCAN COMMAND
# =========================

@tree.command(name="scan")
async def scan(i: discord.Interaction):
    await i.response.send_message("Scanning markets... 📊")

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = get_data(t)

        if not data:
            out.append(f"{t}: ❌ NO DATA")
            continue

        close, high, vol = data

        change = ((close[-1] - close[0]) / close[0]) * 100

        signal = "STRONG" if abs(change) > 2 else "WEAK"

        out.append(f"{t}: {signal} ({change:.2f}%)")

    await i.followup.send("\n".join(out))


# =========================
# BREAKOUT COMMAND (NEW)
# =========================

@tree.command(name="breakout")
async def breakout(i: discord.Interaction):
    await i.response.send_message("Detecting breakouts... ⚡")

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = get_data(t)

        if not data:
            continue

        close, high, vol = data
        result = detect_breakout(high, close, vol)

        if result["breakout"]:
            out.append(f"🚀 {t}: BREAKOUT CONFIRMED")
        elif result["volume_spike"]:
            out.append(f"⚠️ {t}: Volume spike (no breakout)")
        else:
            out.append(f"— {t}: No setup")

    await i.followup.send("\n".join(out))


# =========================
# SIMPLE RATE COMMAND
# =========================

@tree.command(name="rate")
async def rate(i: discord.Interaction, symbol: str):
    await i.response.send_message(f"Analyzing {symbol}...")

    data = get_data(symbol)

    if not data:
        await i.followup.send("No data available")
        return

    close, high, vol = data

    change = ((close[-1] - close[0]) / close[0]) * 100

    if change > 2:
        rating = "BULLISH 📈"
    elif change < -2:
        rating = "BEARISH 📉"
    else:
        rating = "NEUTRAL ⚖️"

    await i.followup.send(f"{symbol}: {rating} ({change:.2f}%)")


# =========================
# READY EVENT (IMPORTANT FIX)
# =========================

@bot.event
async def on_ready():
    await tree.sync()
    print("Slash commands synced")
    print(f"Logged in as {bot.user}")


# =========================
# RUN BOT
# =========================

bot.run(DISCORD_TOKEN)
