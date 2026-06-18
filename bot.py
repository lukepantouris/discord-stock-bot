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

def score(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="6mo")

        close = hist["Close"]
        volume = hist["Volume"]

        price = close.iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]

        vol_ratio = volume.iloc[-1] / volume.rolling(20).mean().iloc[-1]

        score = 0

        if price > sma50:
            score += 3
        if price > close.iloc[-10]:
            score += 2
        if vol_ratio > 1.5:
            score += 2
        if price > close.iloc[-20:].max() * 0.98:
            score += 1

        return min(score, 7)
    except:
        return 0


@tree.command(name="rate", description="Rate a stock")
async def rate(interaction: discord.Interaction, ticker: str):
    s = score(ticker.upper())

    label = "BREAKOUT" if s == 7 else "STRONG" if s >= 5 else "WATCH" if s >= 3 else "WEAK"

    await interaction.response.send_message(
        f"{ticker.upper()} → {s}/7 ({label})"
    )


@tree.command(name="scan", description="Scan top stocks")
async def scan(interaction: discord.Interaction):
    results = [(s, score(s)) for s in stocks]
    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 TOP SETUPS\n\n"
    for r in results[:5]:
        msg += f"{r[0]}: {r[1]}/7\n"

    await interaction.response.send_message(msg)


@client.event
async def on_ready():
    await tree.sync()
    print("Bot is running")


client.run(TOKEN)
