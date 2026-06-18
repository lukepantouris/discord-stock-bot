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

# ---------------- PERSISTENT STORAGE ----------------
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

# ---------------- SECTOR MAP ----------------
sector_map = {
    "NVDA":"AI","AMD":"AI","INTC":"AI","PLTR":"AI","AI":"AI",
    "TSLA":"EV","RIVN":"EV","LCID":"EV","NIO":"EV","XPEV":"EV","LI":"EV",
    "JPM":"BANK","BAC":"BANK","WFC":"BANK","GS":"BANK","MS":"BANK",
    "COIN":"CRYPTO","MSTR":"CRYPTO","RIOT":"CRYPTO","MARA":"CRYPTO",
    "AAPL":"TECH","MSFT":"TECH","GOOGL":"TECH","META":"TECH","AMZN":"TECH"
}

# ---------------- SMART SCORE ENGINE ----------------
def score_stock(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d")

        if hist is None or hist.empty or len(hist) < 3:
            return 5, "NO DATA", [], 0

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        price = close.iloc[-1]
        prev = close.iloc[-2]

        change = (price - prev) / prev if prev != 0 else 0

        vol_avg = volume.mean() if len(volume) else 1
        vol_now = volume.iloc[-1] if len(volume) else vol_avg
        vol_ratio = vol_now / vol_avg if vol_avg else 1

        # ---------------- INSTITUTIONAL SCORING ----------------
        score = 5.0
        reasons = []

        # trend strength
        if change > 0.05:
            score += 2.5
            reasons.append("Strong bullish impulse")
        elif change > 0.02:
            score += 1.5
            reasons.append("Uptrend forming")
        elif change < -0.05:
            score -= 2
            reasons.append("Heavy sell pressure")
        else:
            reasons.append("Neutral trend")

        # volume confirmation
        if vol_ratio > 2.5:
            score += 2.5
            reasons.append("Institutional volume spike")
        elif vol_ratio > 1.5:
            score += 1.5
            reasons.append("Above average participation")

        # stability penalty (removes fake spikes)
        volatility = abs(change)
        if volatility > 0.08:
            score -= 1
            reasons.append("High volatility risk")

        score = max(1, min(int(round(score)), 10))

        if score >= 8:
            label = "🚀 INSTITUTIONAL BREAKOUT"
        elif score >= 6:
            label = "🔥 ACCUMULATION"
        elif score >= 4:
            label = "👀 NEUTRAL"
        else:
            label = "❌ DISTRIBUTION"

        return score, label, reasons, change

    except:
        return 5, "ERROR", ["Data failure"], 0


# ---------------- ASYNC SAFE ----------------
async def safe_score(ticker):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, score_stock, ticker)


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):

    await interaction.response.defer()

    score, label, reasons, change = await safe_score(ticker.upper())

    msg = f"📊 **{ticker.upper()} INSTITUTIONAL ANALYSIS**\n"
    msg += f"{label} → {score}/10\n"
    msg += f"Move: {round(change*100,2)}%\n\n"

    msg += "📌 Signals:\n"
    for r in reasons:
        msg += f"• {r}\n"

    await interaction.followup.send(msg)


# ---------------- /SCAN (SMART FILTERED) ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks[:25]:
        sc, label, _, chg = await safe_score(s)
        results.append((s, sc, label, chg))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 **INSTITUTIONAL MARKET SCAN**\n\n"

    for r in results[:10]:
        msg += f"{r[0]} → {r[1]}/10 {r[2]} ({round(r[3]*100,2)}%)\n"

    await interaction.followup.send(msg)


# ---------------- /SECTOR HEATMAP ----------------
@tree.command(name="sector")
async def sector(interaction: discord.Interaction):

    await interaction.response.defer()

    heat = {}

    for s in stocks[:25]:
        sc, _, _, _ = await safe_score(s)
        sec = sector_map.get(s, "OTHER")

        if sec not in heat:
            heat[sec] = []

        heat[sec].append(sc)

    msg = "📊 **SECTOR HEATMAP**\n\n"

    for sec, scores in heat.items():
        avg = sum(scores) / len(scores)
        msg += f"{sec}: {round(avg,1)}/10\n"

    await interaction.followup.send(msg)


# ---------------- /BREAKOUTS (FILTERED) ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks[:25]:
        sc, label, _, _ = await safe_score(s)
        if sc >= 9:
            results.append((s, sc))

    if not results:
        await interaction.followup.send("No institutional breakouts detected.")
        return

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "🚨 **INSTITUTIONAL BREAKOUTS**\n\n"

    for r in results:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.followup.send(msg)


# ---------------- /WATCH ----------------
@tree.command(name="watch")
async def watch(interaction: discord.Interaction, ticker: str):

    uid = str(interaction.user.id)

    if uid not in user_watchlists:
        user_watchlists[uid] = []

    user_watchlists[uid].append(ticker.upper())
    save_watchlists(user_watchlists)

    await interaction.response.send_message(f"Added {ticker.upper()} to watchlist")


# ---------------- /PORT ----------------
@tree.command(name="port")
async def port(interaction: discord.Interaction):

    uid = str(interaction.user.id)

    if uid not in user_watchlists or not user_watchlists[uid]:
        await interaction.response.send_message("No watchlist found")
        return

    tickers = user_watchlists[uid][:10]

    msg = "📈 YOUR PORTFOLIO\n\n"

    for t in tickers:
        sc, label, _, _ = await safe_score(t)
        msg += f"{t} → {sc}/10 {label}\n"

    await interaction.response.send_message(msg)


# ---------------- WAKE ----------------
@tree.command(name="wake")
async def wake(interaction: discord.Interaction):

    await interaction.response.defer()

    try:
        await tree.sync()
        msg = "Synced successfully"
    except Exception as e:
        msg = str(e)

    await interaction.followup.send(f"🟢 SYSTEM ONLINE\n{msg}")


# ---------------- READY ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("INSTITUTIONAL V5 ONLINE")


# ---------------- RUN ----------------
async def main():
    async with client:
        await client.start(TOKEN)

asyncio.run(main())
