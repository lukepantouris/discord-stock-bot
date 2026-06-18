import discord
from discord import app_commands
import yfinance as yf
import os

# Get token from Render/GitHub Secrets
TOKEN = os.getenv("TOKEN")

# ---- FIXED SETUP ----
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---- STOCK LIST ----
stocks = [
    "NVDA","AMD","PLTR","TSLA","SOFI","AAPL",
    "MSFT","GOOGL","META","AMZN","NFLX",
    "AVGO","MU","QCOM","INTC",
    "RIVN","LCID",
    "JPM","BAC","MS","GS",
    "UNH","LLY","JNJ",
    "COIN","SHOP"
]

# ---- SCORE SYSTEM ----
def score(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="6mo")

        if hist.empty:
            return 0

        close = hist["Close"]
        volume = hist["Volume"]

        price = close.iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]

        vol_avg = volume.rolling(20).mean().iloc[-1]
        vol_now = volume.iloc[-1]

        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 0

        last_10_high = close.iloc[-10:].max()

        score = 0

        # Trend
        if price > sma50:
            score += 3

        # Momentum
        if price >= last_10_high:
            score += 3

        # Volume spike
        if vol_ratio > 2:
            score += 3
        elif vol_ratio > 1.5:
            score += 2
        elif vol_ratio > 1.2:
            score += 1

        return min(score, 10)

    except:
        return 0


# ---- /RATE COMMAND ----
@tree.command(name="rate", description="Rate a stock")
async def rate(interaction: discord.Interaction, ticker: str):
    t = ticker.upper()
    s = score(t)

    if s >= 8:
        label = "🚀 BREAKOUT"
    elif s >= 6:
        label = "🔥 STRONG"
    elif s >= 4:
        label = "👀 WATCH"
    else:
        label = "❌ WEAK"

    await interaction.response.send_message(f"{t} → {s}/10 ({label})")


# ---- /SCAN COMMAND ----
@tree.command(name="scan", description="Scan top stocks")
async def scan(interaction: discord.Interaction):
    results = []

    for s in stocks:
        results.append((s, score(s)))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 TOP STOCKS\n\n"

    for r in results[:7]:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.response.send_message(msg)


# ---- BOT START ----
@client.event
async def on_ready():
    await tree.sync()
    print("Bot is running")


client.run(TOKEN)
