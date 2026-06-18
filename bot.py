import discord
from discord import app_commands
import yfinance as yf
import os
import asyncio
import time

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- WATCHLIST ----------------
stocks = [
    "NVDA","AMD","INTC","TSM","AVGO","ASML","ARM",
    "AAPL","MSFT","GOOGL","META","AMZN","NFLX","TSLA",
    "PLTR","SOFI","UPST","SNOW","CRWD","NET","DDOG","OKTA",
    "RIVN","LCID","NIO","XPEV","LI",
    "COIN","MSTR","RIOT","MARA","HOOD",
    "SQ","PYPL","AFRM",
    "JPM","BAC","WFC","GS","MS",
    "UNH","LLY","JNJ","PFE","MRK","ABBV",
    "WMT","COST","TGT","HD","LOW",
    "NKE","SBUX","MCD","DIS",
    "ADBE","ORCL","CRM","IBM"
]

# ---------------- USER WATCHLIST STORAGE ----------------
user_watchlists = {}

# ---------------- CORE SCORE ----------------
def score_stock(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d")

        if hist is None or hist.empty or len(hist) < 3:
            return 5, "NO DATA", ["No market data"]

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        price = close.iloc[-1]
        prev = close.iloc[-2]

        change = (price - prev) / prev if prev != 0 else 0

        vol_avg = volume.mean() if len(volume) else 1
        vol_now = volume.iloc[-1] if len(volume) else vol_avg
        vol_ratio = vol_now / vol_avg if vol_avg else 1

        score = 5
        reasons = []

        # momentum
        if change > 0.04:
            score += 3
            reasons.append("Strong upward momentum")
        elif change > 0.015:
            score += 2
            reasons.append("Positive movement")
        elif change < -0.04:
            score -= 2
            reasons.append("Strong sell pressure")
        else:
            reasons.append("Neutral movement")

        # volume
        if vol_ratio > 2:
            score += 3
            reasons.append("Heavy volume spike")
        elif vol_ratio > 1.5:
            score += 2
            reasons.append("Above average volume")
        elif vol_ratio > 1.1:
            score += 1

        score = max(1, min(score, 10))

        if score >= 8:
            label = "🚀 BREAKOUT"
        elif score >= 6:
            label = "🔥 STRONG"
        elif score >= 4:
            label = "👀 WATCH"
        else:
            label = "❌ WEAK"

        return score, label, reasons, change

    except:
        return 5, "ERROR", ["Data error"], 0


# ---------------- SAFE WRAPPER ----------------
async def safe_score(ticker):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, score_stock, ticker)


# ---------------- WHY EXPLANATION ENGINE ----------------
def explain(score, change):
    if score >= 8:
        return "Strong breakout momentum with volume confirmation."
    if score >= 6:
        return "Healthy bullish trend forming with steady buying pressure."
    if score >= 4:
        return "Mixed signals — no strong trend confirmation yet."
    return "Weak momentum and low buying interest."


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):

    await interaction.response.defer()

    score, label, reasons, change = await safe_score(ticker.upper())

    msg = f"📊 **{ticker.upper()} ANALYSIS**\n"
    msg += f"{label} → {score}/10\n"
    msg += f"Price Change: {round(change*100,2)}%\n\n"

    msg += "📈 Breakdown:\n"
    for r in reasons:
        msg += f"• {r}\n"

    msg += f"\n🧠 Why:\n{explain(score, change)}"

    await interaction.followup.send(msg)


# ---------------- /SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks[:25]:
        sc, label, _, change = await safe_score(s)
        results.append((s, sc, label, change))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 **MARKET SCAN**\n\n"

    for r in results[:10]:
        msg += f"{r[0]} → {r[1]}/10 {r[2]} ({round(r[3]*100,2)}%)\n"

    await interaction.followup.send(msg)


# ---------------- /BREAKOUTS ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks[:25]:
        sc, label, _, _ = await safe_score(s)
        if sc >= 8:
            results.append((s, sc))

    if not results:
        await interaction.followup.send("No breakouts right now.")
        return

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "🚀 **BREAKOUT ALERTS**\n\n"

    for r in results:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.followup.send(msg)


# ---------------- /WATCHLIST ----------------
@tree.command(name="watch")
async def watch(interaction: discord.Interaction, ticker: str):

    uid = interaction.user.id

    if uid not in user_watchlists:
        user_watchlists[uid] = []

    user_watchlists[uid].append(ticker.upper())

    await interaction.response.send_message(f"Added {ticker.upper()} to your watchlist.")


# ---------------- /COMPARE ----------------
@tree.command(name="compare")
async def compare(interaction: discord.Interaction, stock1: str, stock2: str):

    await interaction.response.defer()

    s1, l1, r1, c1 = await safe_score(stock1.upper())
    s2, l2, r2, c2 = await safe_score(stock2.upper())

    winner = stock1.upper() if s1 > s2 else stock2.upper() if s2 > s1 else "Tie"

    msg = f"{stock1.upper()} → {s1}/10\n"
    msg += f"{stock2.upper()} → {s2}/10\n\n"
    msg += f"🏆 Winner: {winner}"

    await interaction.followup.send(msg)


# ---------------- BACKGROUND BREAKOUT ALERT LOOP ----------------
async def breakout_loop():
    await client.wait_until_ready()

    channel_id = None  # optional: put your Discord channel ID here

    while not client.is_closed():
        try:
            results = []

            for s in stocks[:20]:
                sc, label, _, _ = await safe_score(s)
                if sc >= 9:
                    results.append((s, sc))

            if channel_id:
                channel = client.get_channel(channel_id)

                if channel and results:
                    msg = "🚨 **LIVE BREAKOUT ALERT**\n\n"
                    for r in results:
                        msg += f"{r[0]} → {r[1]}/10\n"
                    await channel.send(msg)

        except:
            pass

        await asyncio.sleep(300)  # every 5 min


# ---------------- KEEP ALIVE LOOP ----------------
async def heartbeat():
    await client.wait_until_ready()

    while not client.is_closed():
        print("heartbeat:", time.ctime())
        await asyncio.sleep(60)


# ---------------- WAKE COMMAND ----------------
@tree.command(name="wake")
async def wake(interaction: discord.Interaction):

    await interaction.response.defer()

    try:
        await tree.sync()
        status = "Synced successfully"
    except Exception as e:
        status = str(e)

    await interaction.followup.send(f"🟢 WAKE OK\n{status}")


# ---------------- READY ----------------
@client.event
async def on_ready():
    try:
        await tree.sync()
        print("Slash commands synced")
    except:
        print("Sync failed")

    print("PRO TRADING BOT ONLINE")


# ---------------- START BOT + TASKS ----------------
async def main():
    async with client:
        client.loop.create_task(breakout_loop())
        client.loop.create_task(heartbeat())
        await client.start(TOKEN)


asyncio.run(main())
