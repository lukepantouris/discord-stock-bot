import discord
from discord import app_commands
import yfinance as yf
import os
import asyncio

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- STOCK LIST ----------------
stocks = [
    "NVDA","AMD","PLTR","TSLA","SOFI","AAPL",
    "MSFT","GOOGL","META","AMZN","NFLX",
    "AVGO","MU","QCOM","INTC",
    "RIVN","LCID","NIO",
    "JPM","BAC","WFC","GS","MS",
    "UNH","LLY","JNJ","PFE","MRK",
    "WMT","COST","TGT","HD","LOW",
    "NKE","SBUX",
    "COIN","MSTR","RIOT","MARA","HOOD",
    "SHOP","SQ","PYPL","ROKU","SPOT",
    "CRWD","SNOW","NET","OKTA","DDOG",
    "ADBE","ORCL"
]

# ---------------- SAFE SCORE (NO CRASH) ----------------
def score(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="6mo")

        if hist is None or hist.empty or len(hist) < 60:
            return 0

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        if len(close) < 20 or len(volume) < 20:
            return 0

        price = close.iloc[-1]

        sma50_series = close.rolling(50).mean().dropna()
        if sma50_series.empty:
            return 0
        sma50 = sma50_series.iloc[-1]

        vol_avg_series = volume.rolling(20).mean().dropna()
        if vol_avg_series.empty:
            return 0
        vol_avg = vol_avg_series.iloc[-1]

        vol_now = volume.iloc[-1]
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 0

        last_10_high = close.iloc[-10:].max()

        s = 0

        if price > sma50:
            s += 3
        if price >= last_10_high:
            s += 3
        if vol_ratio > 2:
            s += 3
        elif vol_ratio > 1.5:
            s += 2
        elif vol_ratio > 1.2:
            s += 1

        return min(s, 10)

    except:
        return 0


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):

    await interaction.response.defer()

    t = ticker.upper()
    s = score(t)

    label = "🚀 BREAKOUT" if s >= 8 else "🔥 STRONG" if s >= 6 else "👀 WATCH" if s >= 4 else "❌ WEAK"

    await interaction.followup.send(f"{t} → {s}/10 ({label})")


# ---------------- /SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):

    await interaction.response.defer()

    results = [(s, score(s)) for s in stocks]
    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 TOP STOCKS\n\n"

    for r in results[:7]:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.followup.send(msg)


# ---------------- /BREAKOUTS ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):

    await interaction.response.defer()

    results = [(s, score(s)) for s in stocks]
    results = [r for r in results if r[1] >= 8]

    if not results:
        await interaction.followup.send("No breakouts right now.")
        return

    msg = "🚀 BREAKOUTS\n\n"

    for r in results:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.followup.send(msg)


# ---------------- /COMPARE ----------------
@tree.command(name="compare")
async def compare(interaction: discord.Interaction, stock1: str, stock2: str):

    await interaction.response.defer()

    s1, s2 = stock1.upper(), stock2.upper()
    sc1, sc2 = score(s1), score(s2)

    winner = s1 if sc1 > sc2 else s2 if sc2 > sc1 else "Tie"

    await interaction.followup.send(
        f"{s1}: {sc1}/10\n{s2}: {sc2}/10\nWinner: {winner}"
    )


# ---------------- BOT READY ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("Bot is running")


client.run(TOKEN)
