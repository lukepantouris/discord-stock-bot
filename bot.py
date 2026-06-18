import discord
from discord import app_commands
import yfinance as yf
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

stocks = [
    "NVDA","AMD","PLTR","TSLA","SOFI","AAPL",
    "MSFT","GOOGL","META","AMZN","NFLX",
    "AVGO","MU","QCOM","INTC",
    "RIVN","LCID",
    "JPM","BAC","MS","GS",
    "UNH","LLY","JNJ",
    "COIN","SHOP"
]

# -----------------------------
# SIMPLE BUT STRONG SCORING
# -----------------------------
def score(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="6mo")

        close = hist["Close"]
        volume = hist["Volume"]

        price = close.iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]

        vol_avg = volume.rolling(20).mean().iloc[-1]
        vol_now = volume.iloc[-1]

        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 0

        last_10_high = close.iloc[-10:].max()

        score = 0

        # Trend (is it going up long-term?)
        if price > sma50:
            score += 3

        # Momentum (recent strength)
        if price >= last_10_high:
            score += 3

        # Volume (real interest from buyers)
        if vol_ratio > 2:
            score += 3
        elif vol_ratio > 1.5:
            score += 2
        elif vol_ratio > 1.2:
            score += 1

        return min(score, 10)

    except:
        return 0


# -----------------------------
# /RATE COMMAND
# -----------------------------
@tree.command(name="rate", description="Rate a stock")
async def rate(interaction: discord.Interaction, ticker: str):
    t = ticker.upper()

    try:
        data = yf.Ticker(t)
        hist = data.history(period="6mo")

        close = hist["Close"]
        volume = hist["Volume"]

        price = close.iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        vol_avg = volume.rolling(20).mean().iloc[-1]
        vol_now = volume.iloc[-1]

        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 0

        s = score(t)

        if s >= 8:
            label = "🚀 BREAKOUT"
        elif s >= 6:
            label = "🔥 STRONG"
        elif s >= 4:
            label = "👀 WATCH"
        else:
            label = "❌ WEAK"

        msg = f"{t} → {s}/10 ({label})\n\n"
        msg += "WHY:\n"
        msg += f"- Above trend (SMA50): {'YES' if price > sma50 else 'NO'}\n"
        msg += f"- Volume spike: {vol_ratio:.2f}x\n"
        msg += f"- Momentum: {'STRONG' if price >= close.iloc[-10:].max() else 'WEAK'}\n"

        await interaction.response.send_message(msg)

    except:
        await interaction.response.send_message("Error checking stock.")


# -----------------------------
# /SCAN COMMAND
# -----------------------------
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


# -----------------------------
# BOT ONLINE
# -----------------------------
@client.event
async def on_ready():
    await tree.sync()
    print("Bot is running")


client.run(TOKEN)
