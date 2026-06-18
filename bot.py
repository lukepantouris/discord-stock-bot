import discord
from discord import app_commands
import yfinance as yf
import os
import asyncio
import json
import time
import psutil

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

WATCH_FILE = "data.json"

# ---------------- MEMORY SYSTEM ----------------
def load_data():
    try:
        with open(WATCH_FILE, "r") as f:
            return json.load(f)
    except:
        return {"watchlists": {}, "alerts": {}}

def save_data(data):
    with open(WATCH_FILE, "w") as f:
        json.dump(data, f)

data = load_data()

# ---------------- STOCK UNIVERSE ----------------
stocks = [
    "NVDA","AMD","INTC","TSM","AVGO","ASML","ARM",
    "AAPL","MSFT","GOOGL","META","AMZN","NFLX","TSLA",
    "PLTR","SOFI","UPST","SNOW","CRWD","NET","DDOG",
    "RIVN","LCID","NIO","XPEV","LI",
    "COIN","MSTR","RIOT","MARA","HOOD",
    "SQ","PYPL","AFRM",
    "JPM","BAC","WFC","GS","MS",
    "UNH","LLY","JNJ","PFE","MRK","ABBV",
    "WMT","COST","TGT","HD","LOW",
    "NKE","SBUX","MCD","DIS",
    "ADBE","ORCL","CRM","IBM"
]

# ---------------- AI SCORE ENGINE ----------------
def score(ticker):
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="5d")

        if h is None or h.empty or len(h) < 3:
            return 0, "NO DATA", [], 0

        c = h["Close"].dropna()
        v = h["Volume"].dropna()

        price = c.iloc[-1]
        prev = c.iloc[-2]

        change = (price - prev) / prev if prev else 0

        vol_avg = v.mean() if len(v) else 1
        vol_now = v.iloc[-1] if len(v) else vol_avg
        ratio = vol_now / vol_avg if vol_avg else 1

        score = 50
        reasons = []

        # momentum
        if change > 0.05:
            score += 20
            reasons.append("Strong momentum")
        elif change > 0.02:
            score += 10
        elif change < -0.05:
            score -= 20
            reasons.append("Sell pressure")

        # volume
        if ratio > 2:
            score += 20
            reasons.append("Institutional volume")
        elif ratio > 1.5:
            score += 10

        # risk filter
        if abs(change) > 0.1:
            score -= 10
            reasons.append("High volatility")

        score = max(0, min(score, 100))

        label = "🚀 BREAKOUT" if score >= 85 else "🔥 STRONG" if score >= 70 else "👀 NEUTRAL" if score >= 50 else "❌ WEAK"

        return score, label, reasons, change

    except:
        return 0, "ERROR", ["API failure"], 0


# ---------------- SAFE ----------------
async def safe(ticker):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, score, ticker)


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    s, l, r, c = await safe(ticker.upper())

    msg = f"📊 {ticker.upper()} ANALYSIS\n{l} → {s}/100\nMove: {round(c*100,2)}%\n\n"

    for x in r:
        msg += f"• {x}\n"

    await interaction.followup.send(msg)


# ---------------- /NEWS ----------------
@tree.command(name="news")
async def news(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    s, l, r, c = await safe(ticker.upper())

    sentiment = "positive" if s > 70 else "neutral" if s > 50 else "negative"

    msg = f"📰 {ticker.upper()} NEWS SUMMARY\n\n"
    msg += f"Market sentiment: {sentiment}\n"
    msg += f"Driver: {'Momentum + volume spike' if s > 70 else 'Mixed signals' if s > 50 else 'Weak demand'}\n"
    msg += f"Change: {round(c*100,2)}%\n"

    await interaction.followup.send(msg)


# ---------------- /CHART ----------------
@tree.command(name="chart")
async def chart(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    t = yf.Ticker(ticker)
    h = t.history(period="5d")

    if h is None or h.empty:
        await interaction.followup.send("No chart data")
        return

    closes = h["Close"].tolist()

    trend = "📈 UP" if closes[-1] > closes[0] else "📉 DOWN"

    msg = f"📊 {ticker.upper()} 5D CHART\n{trend}\n\nPrices:\n"

    for i, p in enumerate(closes):
        msg += f"Day {i+1}: {round(p,2)}\n"

    await interaction.followup.send(msg)


# ---------------- /STATUS ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer()

    mem = psutil.virtual_memory().percent
    cpu = psutil.cpu_percent()

    msg = (
        "🧠 BOT STATUS\n\n"
        f"Latency: {round(client.latency*1000,2)}ms\n"
        f"CPU: {cpu}%\n"
        f"RAM: {mem}%\n"
        f"Watchlists: {len(data['watchlists'])}\n"
    )

    await interaction.followup.send(msg)


# ---------------- /WATCH ----------------
@tree.command(name="watch")
async def watch(interaction: discord.Interaction, ticker: str):

    uid = str(interaction.user.id)

    if uid not in data["watchlists"]:
        data["watchlists"][uid] = []

    data["watchlists"][uid].append(ticker.upper())
    save_data(data)

    await interaction.response.send_message("Added")


# ---------------- /DASHBOARD ----------------
@tree.command(name="dashboard")
async def dashboard(interaction: discord.Interaction):
    await interaction.response.defer()

    results = []

    for s in stocks[:20]:
        sc, l, _, c = await safe(s)
        results.append((s, sc, c))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 MARKET DASHBOARD\n\n"

    msg += "🔥 Top:\n"
    for r in results[:5]:
        msg += f"{r[0]} → {r[1]}/100\n"

    msg += "\n❌ Weak:\n"
    for r in results[-3:]:
        msg += f"{r[0]} → {r[1]}/100\n"

    await interaction.followup.send(msg)


# ---------------- WAKE ----------------
@tree.command(name="wake")
async def wake(interaction: discord.Interaction):
    await interaction.response.defer()
    await tree.sync()
    await interaction.followup.send("ONLINE")


# ---------------- READY ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("V8 ONLINE")


# ---------------- RUN ----------------
async def main():
    async with client:
        await client.start(TOKEN)

asyncio.run(main())
