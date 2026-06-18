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

DATA_FILE = "data.json"

# ---------------- MEMORY ----------------
def load():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {"watchlists": {}}

def save(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f)

data = load()

# ---------------- STOCK UNIVERSE ----------------
stocks = [
    "NVDA","AMD","AAPL","MSFT","TSLA","META","AMZN","GOOGL","NFLX","PLTR",
    "COIN","JPM","BAC","WMT","COST","DIS","INTC","TSM","AVGO","PYPL",
    "SQ","HOOD","MARA","RIOT","SOFI","NIO","RIVN","LCID","IBM","ORCL"
]

# ---------------- CACHE ----------------
cache = {}
CACHE_TIME = 25

def get_cache(t):
    if t in cache:
        v, ts = cache[t]
        if time.time() - ts < CACHE_TIME:
            return v
    return None

def set_cache(t, v):
    cache[t] = (v, time.time())

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


# ---------------- SCORE ENGINE ----------------
def score(ticker):
    d = fetch(ticker)

    if not d:
        return 5, "NO DATA", ["API issue"], 0

    price, change, vol_ratio = d

    s = 50
    r = []

    if change > 0.05:
        s += 20
        r.append("Strong momentum")
    elif change < -0.05:
        s -= 20
        r.append("Sell pressure")

    if vol_ratio > 2:
        s += 20
        r.append("Institutional volume")

    s = max(0, min(100, s))

    label = "🚀 BREAKOUT" if s >= 85 else "🔥 STRONG" if s >= 70 else "👀 NEUTRAL" if s >= 50 else "❌ WEAK"

    return s, label, r, change


async def safe(t):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, score, t)


# ---------------- RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    s, l, r, c = await safe(ticker.upper())

    msg = f"📊 {ticker.upper()} ANALYSIS\n{l} → {s}/100\nMove: {round(c*100,2)}%\n\n"

    for x in r:
        msg += f"• {x}\n"

    await interaction.followup.send(msg)


# ---------------- SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):
    await interaction.response.defer()

    out = []

    for s in stocks:
        sc, l, r, c = await safe(s)
        out.append((s, sc, c))

    out.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 MARKET SCAN\n\n"

    for r in out[:10]:
        msg += f"{r[0]} → {r[1]}/100 ({round(r[2]*100,2)}%)\n"

    await interaction.followup.send(msg)


# ---------------- BREAKOUTS (FIXED + ADDED BACK) ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):
    await interaction.response.defer()

    found = []

    for s in stocks:
        sc, l, r, c = await safe(s)
        if sc >= 85:
            found.append((s, sc))

    if not found:
        await interaction.followup.send("No strong breakouts right now.")
        return

    found.sort(key=lambda x: x[1], reverse=True)

    msg = "🚨 BREAKOUT WATCH\n\n"

    for f in found:
        msg += f"{f[0]} → {f[1]}/100\n"

    await interaction.followup.send(msg)


# ---------------- NEWS (ADDED BACK) ----------------
@tree.command(name="news")
async def news(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()

    s, l, r, c = await safe(ticker.upper())

    sentiment = "bullish" if s > 70 else "neutral" if s > 50 else "bearish"

    msg = f"📰 {ticker.upper()} NEWS SNAPSHOT\n\n"
    msg += f"Sentiment: {sentiment}\n"
    msg += f"Driver: {'Momentum + volume' if s > 70 else 'Mixed signals'}\n"
    msg += f"Move: {round(c*100,2)}%\n"

    await interaction.followup.send(msg)


# ---------------- CHART (ADDED BACK) ----------------
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

    msg = f"📊 {ticker.upper()} CHART\n{trend}\n\n"

    for i, p in enumerate(closes):
        msg += f"Day {i+1}: {round(p,2)}\n"

    await interaction.followup.send(msg)


# ---------------- DASHBOARD (ADDED BACK) ----------------
@tree.command(name="dashboard")
async def dashboard(interaction: discord.Interaction):
    await interaction.response.defer()

    res = []

    for s in stocks[:15]:
        sc, l, r, c = await safe(s)
        res.append((s, sc))

    res.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 MARKET DASHBOARD\n\n"

    msg += "🔥 Top Movers:\n"
    for r in res[:5]:
        msg += f"{r[0]} → {r[1]}/100\n"

    msg += "\n❌ Weak:\n"
    for r in res[-3:]:
        msg += f"{r[0]} → {r[1]}/100\n"

    await interaction.followup.send(msg)


# ---------------- WATCH ----------------
@tree.command(name="watch")
async def watch(interaction: discord.Interaction, ticker: str):
    uid = str(interaction.user.id)

    if uid not in data["watchlists"]:
        data["watchlists"][uid] = []

    data["watchlists"][uid].append(ticker.upper())
    save(data)

    await interaction.response.send_message(f"Added {ticker.upper()}")


# ---------------- STATUS ----------------
@tree.command(name="status")
async def status(interaction: discord.Interaction):
    await interaction.response.defer()

    msg = (
        "🧠 SYSTEM STATUS\n\n"
        f"Latency: {round(client.latency*1000,2)}ms\n"
        f"Cache size: {len(cache)} items\n"
        f"Watchlists: {len(data['watchlists'])}\n"
    )

    await interaction.followup.send(msg)


# ---------------- WAKE (FORCE SYNC FIX) ----------------
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
    try:
        synced = await tree.sync()
        print(f"SYNCED {len(synced)} COMMANDS")
    except Exception as e:
        print("SYNC ERROR:", e)

    print("BOT ONLINE (FULL V9 RESTORE)")


# ---------------- RUN ----------------
async def main():
    async with client:
        await client.start(TOKEN)

asyncio.run(main())
