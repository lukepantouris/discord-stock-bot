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
    "AAPL","MSFT","AMZN","NVDA","TSLA","META","GOOGL","NFLX","AMD","INTC",
    "PLTR","COIN","JPM","BAC","WMT","COST","DIS","TSM","AVGO","PYPL",
    "SQ","HOOD","MARA","RIOT","SOFI","NIO","RIVN","LCID","ORCL","IBM"
]

# ---------------- FETCH STOCK ----------------
def get_stock(ticker):
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="5d")

        if h is None or h.empty:
            return None

        close = h["Close"]

        price = close.iloc[-1]
        prev = close.iloc[-2] if len(close) > 1 else price

        change = (price - prev) / prev if prev else 0

        return price, change

    except:
        return None


# ---------------- SCORE SYSTEM ----------------
def score_stock(ticker):
    d = get_stock(ticker)

    if not d:
        return 0, "NO DATA", []

    price, change = d

    score = 50
    reasons = []

    if change > 0.05:
        score += 25
        reasons.append("Strong momentum")
    elif change < -0.05:
        score -= 25
        reasons.append("Sell pressure")

    score = max(0, min(100, score))

    # ✅ FIXED LABEL LOGIC
    if score >= 85:
        label = "🚀 BREAKOUT"
    elif score >= 70:
        label = "🔥 STRONG"
    elif score >= 50:
        label = "👀 NEUTRAL"
    else:
        label = "❌ WEAK"

    return score, label, reasons


async def safe_run(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


# ---------------- RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    score, label, reasons = await safe_run(score_stock, ticker.upper())

    msg = f"📊 {ticker.upper()}\n{label} → {score}/100\n\n"

    if reasons:
        for r in reasons:
            msg += f"• {r}\n"

    await interaction.followup.send(msg)


# ---------------- SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):
    await interaction.response.defer()

    results = []

    for s in stocks:
        score, label, _ = await safe_run(score_stock, s)
        results.append((s, score, label))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 MARKET SCAN\n\n"

    for r in results[:10]:
        msg += f"{r[0]} → {r[1]}/100 {r[2]}\n"

    await interaction.followup.send(msg)


# ---------------- BREAKOUTS ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):
    await interaction.response.defer()

    found = []

    for s in stocks:
        score, label, _ = await safe_run(score_stock, s)
        if score >= 85:
            found.append((s, score))

    if not found:
        await interaction.followup.send("No breakouts right now.")
        return

    msg = "🚨 BREAKOUTS\n\n"

    for f in found:
        msg += f"{f[0]} → {f[1]}/100\n"

    await interaction.followup.send(msg)


# ---------------- NEWS (SIMPLE SENTIMENT) ----------------
@tree.command(name="news")
async def news(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    score, label, _ = await safe_run(score_stock, ticker.upper())

    sentiment = "bullish" if score > 70 else "neutral" if score > 50 else "bearish"

    msg = f"📰 {ticker.upper()}\nSentiment: {sentiment}\nRating: {label}"

    await interaction.followup.send(msg)


# ---------------- STATUS ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer()

    msg = (
        "🧠 BOT STATUS\n\n"
        f"Latency: {round(client.latency*1000,2)}ms\n"
        f"Tracked Stocks: {len(stocks)}\n"
        "System: Online"
    )

    await interaction.followup.send(msg)


# ---------------- WAKE ----------------
@tree.command(name="wake")
async def wake(interaction: discord.Interaction):
    await interaction.response.defer()

    synced = await tree.sync()

    await interaction.followup.send(f"🟢 Awake\nSynced {len(synced)} commands")


# ---------------- READY ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("BOT ONLINE")


# ---------------- START ----------------
async def main():
    await client.start(TOKEN)

asyncio.run(main())
