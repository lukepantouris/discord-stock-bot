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

# ---------------- STOCK DATA ----------------
def get_stock(ticker):
    try:
        data = yf.Ticker(ticker).history(period="5d")

        if data is None or data.empty:
            return None

        close = data["Close"]

        price = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else price

        change = (price - prev) / prev if prev != 0 else 0

        return price, change

    except:
        return None


# ---------------- SCORE SYSTEM ----------------
def score_stock(ticker):
    data = get_stock(ticker)

    if not data:
        return 0, "NO DATA", []

    price, change = data

    score = 50
    reasons = []

    # momentum logic
    if change > 0.05:
        score += 25
        reasons.append("Strong upward momentum")
    elif change < -0.05:
        score -= 25
        reasons.append("Heavy selling pressure")

    score = max(0, min(100, score))

    # ✅ FIXED LABEL LOGIC (NO CRASH)
    if score >= 85:
        label = "🚀 BREAKOUT"
    elif score >= 70:
        label = "🔥 STRONG"
    elif score >= 50:
        label = "👀 NEUTRAL"
    else:
        label = "❌ WEAK"

    return score, label, reasons


# ---------------- SAFE EXECUTION ----------------
async def run_blocking(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


# ---------------- RATE COMMAND ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    score, label, reasons = await run_blocking(score_stock, ticker.upper())

    msg = f"📊 **{ticker.upper()}**\n{label} → {score}/100\n\n"

    for r in reasons:
        msg += f"• {r}\n"

    await interaction.followup.send(msg)


# ---------------- SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):
    await interaction.response.defer()

    results = []

    for s in stocks:
        score, label, _ = await run_blocking(score_stock, s)
        results.append((s, score, label))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 **MARKET SCAN**\n\n"

    for r in results[:10]:
        msg += f"{r[0]} → {r[1]}/100 {r[2]}\n"

    await interaction.followup.send(msg)


# ---------------- BREAKOUTS ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):
    await interaction.response.defer()

    found = []

    for s in stocks:
        score, label, _ = await run_blocking(score_stock, s)
        if score >= 85:
            found.append((s, score))

    if not found:
        await interaction.followup.send("No breakouts right now.")
        return

    msg = "🚨 **BREAKOUT ALERTS**\n\n"

    for f in found:
        msg += f"{f[0]} → {f[1]}/100\n"

    await interaction.followup.send(msg)


# ---------------- NEWS (simple sentiment) ----------------
@tree.command(name="news")
async def news(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    score, label, _ = await run_blocking(score_stock, ticker.upper())

    sentiment = "bullish 📈" if score > 70 else "neutral ⚖️" if score > 50 else "bearish 📉"

    await interaction.followup.send(
        f"📰 **{ticker.upper()} NEWS VIEW**\n"
        f"Sentiment: {sentiment}\n"
        f"Rating: {label}"
    )


# ---------------- STATUS ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer()

    await interaction.followup.send(
        "🟢 BOT STATUS\n\n"
        f"Latency: {round(client.latency * 1000, 2)}ms\n"
        f"Tracked Stocks: {len(stocks)}\n"
        "System: Online"
    )


# ---------------- WAKE ----------------
@tree.command(name="wake")
async def wake(interaction: discord.Interaction):
    await interaction.response.defer()

    synced = await tree.sync()

    await interaction.followup.send(f"🟢 Awake | Synced {len(synced)} commands")


# ---------------- READY ----------------
@client.event
async def on_ready():
    try:
        await tree.sync()
        print("BOT ONLINE")
    except Exception as e:
        print("SYNC ERROR:", e)


# ---------------- START ----------------
async def main():
    if not TOKEN:
        print("TOKEN NOT FOUND")
        return

    await client.start(TOKEN)


asyncio.run(main())
