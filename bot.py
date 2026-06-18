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

# ---------------- PRICE ENGINE ----------------
def get_price_data(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d")

        if hist is None or hist.empty:
            return None

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        price = close.iloc[-1]
        prev = close.iloc[-2] if len(close) > 1 else price

        change = (price - prev) / prev if prev else 0

        return price, change, volume

    except:
        return None


# ---------------- INSTITUTIONAL SCORE ----------------
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

        change = (price - prev) / prev if prev else 0

        vol_avg = volume.mean() if len(volume) else 1
        vol_now = volume.iloc[-1] if len(volume) else vol_avg
        vol_ratio = vol_now / vol_avg if vol_avg else 1

        score = 5
        reasons = []

        # trend
        if change > 0.05:
            score += 2.5
            reasons.append("Strong bullish momentum")
        elif change > 0.02:
            score += 1.5
            reasons.append("Uptrend forming")
        elif change < -0.05:
            score -= 2
            reasons.append("Strong sell pressure")
        else:
            reasons.append("Neutral trend")

        # volume
        if vol_ratio > 2.5:
            score += 2.5
            reasons.append("Institutional volume spike")
        elif vol_ratio > 1.5:
            score += 1.5
            reasons.append("Above average volume")

        # volatility filter
        if abs(change) > 0.1:
            score -= 1
            reasons.append("High volatility risk")

        score = max(1, min(int(round(score)), 10))

        if score >= 8:
            label = "🚀 BREAKOUT"
        elif score >= 6:
            label = "🔥 ACCUMULATION"
        elif score >= 4:
            label = "👀 NEUTRAL"
        else:
            label = "❌ DISTRIBUTION"

        return score, label, reasons, change

    except:
        return 5, "ERROR", ["Data failure"], 0


# ---------------- SAFE WRAPPER ----------------
async def safe_score(ticker):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, score_stock, ticker)


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):

    await interaction.response.defer()

    score, label, reasons, change = await safe_score(ticker.upper())

    price_data = get_price_data(ticker.upper())

    msg = f"📊 **{ticker.upper()} INSTITUTIONAL ANALYSIS**\n"
    msg += f"{label} → {score}/10\n"
    msg += f"Move: {round(change*100,2)}%\n"

    if price_data:
        price, _, _ = price_data
        msg += f"Price: ${round(price,2)}\n"

    msg += "\n📌 Signals:\n"
    for r in reasons:
        msg += f"• {r}\n"

    # AI-style explanation
    if score >= 8:
        msg += "\n🧠 Why: Strong institutional buying pressure + momentum continuation."
    elif score >= 6:
        msg += "\n🧠 Why: Accumulation phase with volume confirmation."
    elif score >= 4:
        msg += "\n🧠 Why: Mixed signals, no clear trend."
    else:
        msg += "\n🧠 Why: Distribution phase or weak demand."

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

    msg = "📊 **INSTITUTIONAL MARKET SCAN v6**\n\n"

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
        if sc >= 9:
            results.append((s, sc))

    if not results:
        await interaction.followup.send("No institutional breakouts right now.")
        return

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "🚨 **INSTITUTIONAL BREAKOUTS**\n\n"

    for r in results:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.followup.send(msg)


# ---------------- WATCH ----------------
@tree.command(name="watch")
async def watch(interaction: discord.Interaction, ticker: str):

    uid = str(interaction.user.id)

    if uid not in user_watchlists:
        user_watchlists[uid] = []

    user_watchlists[uid].append(ticker.upper())
    save_watchlists(user_watchlists)

    await interaction.response.send_message(f"Added {ticker.upper()} to watchlist")


# ---------------- PORTFOLIO ANALYSIS ----------------
@tree.command(name="port")
async def port(interaction: discord.Interaction):

    uid = str(interaction.user.id)

    if uid not in user_watchlists or not user_watchlists[uid]:
        await interaction.response.send_message("No watchlist found.")
        return

    tickers = user_watchlists[uid][:10]

    scores = []

    msg = "📈 **PORTFOLIO ANALYSIS v6**\n\n"

    for t in tickers:
        sc, label, _, _ = await safe_score(t)
        scores.append(sc)
        msg += f"{t} → {sc}/10 {label}\n"

    avg = sum(scores) / len(scores)

    msg += f"\n📊 Portfolio Strength: {round(avg,1)}/10"

    await interaction.response.send_message(msg)


# ---------------- SECTOR HEATMAP ----------------
@tree.command(name="sector")
async def sector(interaction: discord.Interaction):

    await interaction.response.defer()

    heat = {}

    for s in stocks[:25]:
        sc, _, _, _ = await safe_score(s)
        sec = "OTHER"

        if s in ["NVDA","AMD","AAPL","MSFT","GOOGL","META"]:
            sec = "TECH"
        elif s in ["JPM","BAC","GS","MS"]:
            sec = "BANK"
        elif s in ["COIN","MSTR","RIOT"]:
            sec = "CRYPTO"

        if sec not in heat:
            heat[sec] = []

        heat[sec].append(sc)

    msg = "📊 **SECTOR HEATMAP v6**\n\n"

    for k,v in heat.items():
        msg += f"{k}: {round(sum(v)/len(v),1)}/10\n"

    await interaction.followup.send(msg)


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
    print("INSTITUTIONAL V6 ONLINE")


# ---------------- RUN ----------------
async def main():
    async with client:
        await client.start(TOKEN)

asyncio.run(main())
