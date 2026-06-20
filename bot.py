import os
import discord
from discord import app_commands
from discord.ext import commands
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

# ONLY set headers if keys exist (IMPORTANT FIX)
headers = {}
if ALPACA_KEY and ALPACA_SECRET:
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }


# =========================
# BOT SETUP (FIXED PROPERLY)
# =========================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# =========================
# HELP COMMAND
# =========================

@tree.command(name="help")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Commands**\n"
        "/help - show commands\n"
        "/scan - scan stocks\n"
    )


# =========================
# DATA FETCH (SAFE)
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

            try:
                data = r.json()
            except:
                continue

            bars = data.get("bars", [])

            if not bars:
                continue

            close = [b["c"] for b in bars if b.get("c") is not None]

            if len(close) >= 5:
                return close

        return None

    except Exception as e:
        print("DATA ERROR:", e)
        return None


# =========================
# SCAN COMMAND (FIXED)
# =========================

@tree.command(name="scan")
async def scan(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]
    out = []

    for t in tickers:
        data = get_data(t)

        if not data:
            out.append(f"{t}: ❌ NO DATA")
            continue

        try:
            change = ((data[-1] - data[0]) / data[0]) * 100
        except:
            continue

        label = "STRONG" if abs(change) > 2 else "WEAK"
        out.append(f"{t}: {label} ({change:.2f}%)")

    if len(out) == 0:
        out = ["No market data available"]

    await interaction.followup.send("\n".join(out))


# =========================
# SYNC FIX (VERY IMPORTANT)
# =========================

@bot.event
async def setup_hook():
    await tree.sync()
    print("Slash commands synced (setup_hook)")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
