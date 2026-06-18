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

# ---------------- LOAD WATCHLISTS (PERSISTENT) ----------------
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

# ---------------- STOCK UNIVERSE ----------------
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

# ---------------- CORE SCORING ENGINE ----------------
def score_stock(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d")

        if hist is None or hist.empty or len(hist) < 3:
            return 5, "NO DATA", ["No data available"], 0

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
        if change > 0.05:
            score += 3
            reasons.append("Strong bullish momentum")
        elif change > 0.02:
            score += 2
            reasons.append("Positive momentum building")
        elif change < -0.05:
            score -= 2
            reasons.append("Strong sell pressure")
        else:
            reasons.append("Neutral movement")

        # volume
        if vol_ratio > 2:
            score += 3
            reasons.append("Institutional volume spike")
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
        return 5, "ERROR", ["Data fetch failed"], 0


# ---------------- ASYNC WRAPPER ----------------
async def safe_score(ticker):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, score_stock, ticker)


# ---------------- EMBED BUILDER ----------------
def build_embed(title, score, label, change, reasons):
    embed = discord.Embed(title=title, color=0x00ff99)

    embed.add_field(name="Score", value=f"{label} → {score}/10", inline=False)
    embed.add_field(name="Change", value=f"{round(change*100,2)}%", inline=False)

    embed.add_field(
        name="Reasons",
        value="\n".join([f"• {r}" for r in reasons]),
        inline=False
    )

    return embed


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):

    await interaction.response.defer()

    score, label, reasons, change = await safe_score(ticker.upper())

    embed = build_embed(
        f"{ticker.upper()} ANALYSIS",
        score,
        label,
        change,
        reasons
    )

    await interaction.followup.send(embed=embed)


# ---------------- /SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks[:25]:
        sc, label, _, change = await safe_score(s)
        results.append((s, sc, label, change))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = ""
    for r in results[:10]:
        msg += f"**{r[0]}** → {r[1]}/10 {r[2]} ({round(r[3]*100,2)}%)\n"

    embed = discord.Embed(
        title="📊 MARKET SCAN",
        description=msg,
        color=0x3498db
    )

    await interaction.followup.send(embed=embed)


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

    msg = "\n".join([f"🚀 {r[0]} → {r[1]}/10" for r in results])

    embed = discord.Embed(
        title="🚨 BREAKOUT ALERTS",
        description=msg,
        color=0xff0000
    )

    await interaction.followup.send(embed=embed)


# ---------------- /WATCH ----------------
@tree.command(name="watch")
async def watch(interaction: discord.Interaction, ticker: str):

    uid = str(interaction.user.id)

    if uid not in user_watchlists:
        user_watchlists[uid] = []

    user_watchlists[uid].append(ticker.upper())
    save_watchlists(user_watchlists)

    await interaction.response.send_message(
        f"✅ Added {ticker.upper()} to your watchlist."
    )


# ---------------- /COMPARE ----------------
@tree.command(name="compare")
async def compare(interaction: discord.Interaction, stock1: str, stock2: str):

    await interaction.response.defer()

    s1, l1, r1, c1 = await safe_score(stock1.upper())
    s2, l2, r2, c2 = await safe_score(stock2.upper())

    winner = stock1.upper() if s1 > s2 else stock2.upper() if s2 > s1 else "Tie"

    msg = f"{stock1.upper()} → {s1}/10\n{stock2.upper()} → {s2}/10\n\n🏆 {winner}"

    embed = discord.Embed(
        title="⚔️ STOCK COMPARISON",
        description=msg,
        color=0x9b59b6
    )

    await interaction.followup.send(embed=embed)


# ---------------- LIVE ALERT LOOP ----------------
ALERT_CHANNEL_ID = None  # PUT YOUR CHANNEL ID HERE

async def alert_loop():
    await client.wait_until_ready()

    while not client.is_closed():

        try:
            alerts = []

            for s in stocks[:20]:
                sc, label, _, _ = await safe_score(s)
                if sc >= 9:
                    alerts.append((s, sc))

            if ALERT_CHANNEL_ID and alerts:
                channel = client.get_channel(ALERT_CHANNEL_ID)

                if channel:
                    msg = "🚨 **LIVE BREAKOUT ALERT**\n\n"
                    for a in alerts:
                        msg += f"{a[0]} → {a[1]}/10\n"

                    await channel.send(msg)

        except:
            pass

        await asyncio.sleep(300)


# ---------------- KEEP ALIVE ----------------
async def heartbeat():
    await client.wait_until_ready()

    while not client.is_closed():
        print("heartbeat:", time.ctime())
        await asyncio.sleep(60)


# ---------------- WAKE ----------------
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
    await tree.sync()
    print("PRO TRADING SYSTEM V4 ONLINE")


# ---------------- RUN ----------------
async def main():
    async with client:
        client.loop.create_task(alert_loop())
        client.loop.create_task(heartbeat())
        await client.start(TOKEN)

asyncio.run(main())
