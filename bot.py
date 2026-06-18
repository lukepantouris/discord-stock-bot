import discord
from discord import app_commands
import yfinance as yf
import os
import asyncio
import json
import time

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

WATCH_FILE = "data.json"

# ---------------- STORAGE ----------------
def load_data():
    try:
        with open(WATCH_FILE, "r") as f:
            return json.load(f)
    except:
        return {"watchlists": {}}

def save_data(data):
    with open(WATCH_FILE, "w") as f:
        json.dump(data, f)

data = load_data()

# ---------------- STOCK UNIVERSE ----------------
stocks = [
    "NVDA","AMD","AAPL","MSFT","TSLA","META","AMZN","GOOGL","NFLX","PLTR",
    "COIN","JPM","BAC","WMT","COST","DIS","AMD","INTC","TSM","AVGO",
    "PYPL","SQ","HOOD","MARA","RIOT"
]

# ---------------- CACHE ----------------
cache = {}
CACHE_TIME = 30

def get_cache(t):
    if t in cache:
        val, ts = cache[t]
        if time.time() - ts < CACHE_TIME:
            return val
    return None

def set_cache(t, val):
    cache[t] = (val, time.time())

# ---------------- FETCH ----------------
def fetch(ticker):
    try:
        cached = get_cache(ticker)
        if cached:
            return cached

        t = yf.Ticker(ticker)
        h = t.history(period="5d")

        if h is None or h.empty:
            return None

        close = h["Close"].dropna()
        vol = h["Volume"].dropna()

        price = close.iloc[-1]
        prev = close.iloc[-2] if len(close) > 1 else price

        change = (price - prev) / prev if prev else 0

        vol_avg = vol.mean() if len(vol) else 1
        vol_now = vol.iloc[-1] if len(vol) else vol_avg
        vol_ratio = vol_now / vol_avg if vol_avg else 1

        result = (price, change, vol_ratio)
        set_cache(ticker, result)

        return result

    except:
        return None


# ---------------- SCORE ----------------
def score_stock(ticker):
    try:
        d = fetch(ticker)

        if not d:
            return 5, "NO DATA", ["API error"], 0

        price, change, vol_ratio = d

        score = 50
        reasons = []

        if change > 0.05:
            score += 20
            reasons.append("Strong momentum")
        elif change < -0.05:
            score -= 20
            reasons.append("Sell pressure")

        if vol_ratio > 2:
            score += 20
            reasons.append("Institutional volume")

        score = max(0, min(100, score))

        label = "🚀 BREAKOUT" if score >= 85 else "🔥 STRONG" if score >= 70 else "👀 NEUTRAL" if score >= 50 else "❌ WEAK"

        return score, label, reasons, change

    except Exception as e:
        return 0, "ERROR", [str(e)[:40]], 0


async def safe(t):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, score_stock, t)


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    s, l, r, c = await safe(ticker.upper())

    msg = f"📊 {ticker.upper()} ANALYSIS\n"
    msg += f"{l} → {s}/100\n"
    msg += f"Move: {round(c*100,2)}%\n\n"

    for x in r:
        msg += f"• {x}\n"

    await interaction.followup.send(msg)


# ---------------- /SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):
    await interaction.response.defer()

    results = []

    for s in stocks:
        sc, l, r, c = await safe(s)
        results.append((s, sc, c))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 MARKET SCAN\n\n"

    for r in results[:10]:
        msg += f"{r[0]} → {r[1]}/100 ({round(r[2]*100,2)}%)\n"

    await interaction.followup.send(msg)


# ---------------- /WATCH ----------------
@tree.command(name="watch")
async def watch(interaction: discord.Interaction, ticker: str):
    uid = str(interaction.user.id)

    if uid not in data["watchlists"]:
        data["watchlists"][uid] = []

    data["watchlists"][uid].append(ticker.upper())
    save_data(data)

    await interaction.response.send_message(f"Added {ticker.upper()}")


# ---------------- /STATUS (FIXED - NO psutil) ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer()

    latency = round(client.latency * 1000, 2)

    # safe "fake memory stats" (Render-safe)
    mem_status = "N/A (Render free tier restriction)"

    msg = (
        "🧠 BOT STATUS\n\n"
        f"Latency: {latency}ms\n"
        f"Cache Size: {len(cache)} items\n"
        f"Watchlists: {len(data['watchlists'])}\n"
        f"Memory: {mem_status}\n"
    )

    await interaction.followup.send(msg)


# ---------------- WAKE ----------------
@tree.command(name="wake")
async def wake(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        synced = await tree.sync()
        msg = f"Synced {len(synced)} commands"
    except Exception as e:
        msg = str(e)

    await interaction.followup.send("🟢 ONLINE\n" + msg)


# ---------------- READY ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("BOT RUNNING (FIXED RENDER VERSION)")


# ---------------- RUN ----------------
async def main():
    async with client:
        await client.start(TOKEN)

asyncio.run(main())
