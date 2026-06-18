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

WATCH_FILE = "watchlists.json"

# ---------------- STORAGE ----------------
def load_watchlists():
    try:
        with open(WATCH_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_watchlists(data):
    with open(WATCH_FILE, "w") as f:
        json.dump(data, f)

user_watchlists = load_watchlists()

# ---------------- UNIVERSE ----------------
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
def ai_score(ticker):
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="5d")

        if h is None or h.empty or len(h) < 3:
            return 0, "NO DATA", ["Not enough data"]

        close = h["Close"].dropna()
        volume = h["Volume"].dropna()

        price = close.iloc[-1]
        prev = close.iloc[-2]

        change = (price - prev) / prev if prev else 0

        vol_avg = volume.mean() if len(volume) else 1
        vol_now = volume.iloc[-1] if len(volume) else vol_avg
        vol_ratio = vol_now / vol_avg if vol_avg else 1

        score = 50  # AI BASELINE (0–100)
        reasons = []

        # ---------------- MOMENTUM ----------------
        if change > 0.05:
            score += 20
            reasons.append("Strong breakout momentum")
        elif change > 0.02:
            score += 10
            reasons.append("Uptrend forming")
        elif change < -0.05:
            score -= 20
            reasons.append("Heavy sell pressure")

        # ---------------- VOLUME ----------------
        if vol_ratio > 2.5:
            score += 20
            reasons.append("Institutional volume spike")
        elif vol_ratio > 1.5:
            score += 10
            reasons.append("Above average participation")

        # ---------------- RISK FILTER ----------------
        volatility = abs(change)
        if volatility > 0.1:
            score -= 15
            reasons.append("High volatility risk")

        score = max(0, min(score, 100))

        if score >= 85:
            label = "🚀 AI BREAKOUT"
        elif score >= 70:
            label = "🔥 STRONG ACCUMULATION"
        elif score >= 50:
            label = "👀 NEUTRAL"
        else:
            label = "❌ WEAK"

        return score, label, reasons, change

    except:
        return 0, "ERROR", ["Data failure"], 0


# ---------------- ASYNC WRAPPER ----------------
async def safe_score(ticker):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ai_score, ticker)


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):

    await interaction.response.defer()

    score, label, reasons, change = await safe_score(ticker.upper())

    msg = f"📊 **AI ANALYSIS: {ticker.upper()}**\n"
    msg += f"{label} → {score}/100\n"
    msg += f"Move: {round(change*100,2)}%\n\n"

    msg += "📌 Signals:\n"
    for r in reasons:
        msg += f"• {r}\n"

    await interaction.followup.send(msg)


# ---------------- /SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks[:25]:
        sc, label, _, chg = await safe_score(s)
        results.append((s, sc, label, chg))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 **AI MARKET SCAN v7**\n\n"

    for r in results[:10]:
        msg += f"{r[0]} → {r[1]}/100 {r[2]} ({round(r[3]*100,2)}%)\n"

    await interaction.followup.send(msg)


# ---------------- /BREAKOUTS ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks[:25]:
        sc, label, _, _ = await safe_score(s)
        if sc >= 85:
            results.append((s, sc))

    if not results:
        await interaction.followup.send("No AI breakouts right now.")
        return

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "🚨 **AI BREAKOUTS (INSTITUTIONAL)**\n\n"

    for r in results:
        msg += f"{r[0]} → {r[1]}/100\n"

    await interaction.followup.send(msg)


# ---------------- /WATCH ----------------
@tree.command(name="watch")
async def watch(interaction: discord.Interaction, ticker: str):

    uid = str(interaction.user.id)

    if uid not in user_watchlists:
        user_watchlists[uid] = []

    user_watchlists[uid].append(ticker.upper())
    save_watchlists(user_watchlists)

    await interaction.response.send_message(f"Added {ticker.upper()}")


# ---------------- /PORT ----------------
@tree.command(name="port")
async def port(interaction: discord.Interaction):

    uid = str(interaction.user.id)

    if uid not in user_watchlists:
        await interaction.response.send_message("No watchlist.")
        return

    tickers = user_watchlists[uid][:10]

    scores = []

    msg = "📈 **AI PORTFOLIO v7**\n\n"

    for t in tickers:
        sc, label, _, _ = await safe_score(t)
        scores.append(sc)
        msg += f"{t} → {sc}/100 {label}\n"

    avg = sum(scores) / len(scores)

    msg += f"\n📊 Portfolio Strength: {round(avg,1)}/100"

    await interaction.response.send_message(msg)


# ---------------- LIVE ALERT ENGINE ----------------
ALERT_CHANNEL_ID = None  # set your channel id

async def alert_loop():
    await client.wait_until_ready()

    while not client.is_closed():

        try:
            alerts = []

            for s in stocks[:20]:
                sc, label, _, _ = await safe_score(s)

                if sc >= 90:
                    alerts.append((s, sc))

            if ALERT_CHANNEL_ID and alerts:
                channel = client.get_channel(ALERT_CHANNEL_ID)

                if channel:
                    msg = "🚨 **AI BREAKOUT ALERT**\n\n"
                    for a in alerts:
                        msg += f"{a[0]} → {a[1]}/100\n"

                    await channel.send(msg)

        except:
            pass

        await asyncio.sleep(300)


# ---------------- WAKE ----------------
@tree.command(name="wake")
async def wake(interaction: discord.Interaction):

    await interaction.response.defer()
    await tree.sync()

    await interaction.followup.send("🟢 AI SYSTEM ONLINE")


# ---------------- READY ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("HEDGE FUND AI V7 ONLINE")


# ---------------- RUN ----------------
async def main():
    async with client:
        client.loop.create_task(alert_loop())
        await client.start(TOKEN)

asyncio.run(main())
