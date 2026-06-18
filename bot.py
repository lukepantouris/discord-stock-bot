import discord
from discord import app_commands
import yfinance as yf
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- EXPANDED WATCHLIST (+20 stocks) ----------------
stocks = [
    # mega tech
    "NVDA","AMD","INTC","TSM","AVGO","ASML","ARM",

    # big tech
    "AAPL","MSFT","GOOGL","META","AMZN","NFLX","TSLA",

    # AI / growth
    "PLTR","SOFI","UPST","SNOW","CRWD","NET","DDOG","OKTA","AI",

    # EV
    "RIVN","LCID","NIO","XPEV","LI",

    # crypto / retail trading
    "COIN","MSTR","RIOT","MARA","HOOD","BTBT",

    # fintech
    "SQ","PYPL","AFRM",

    # banks
    "JPM","BAC","WFC","GS","MS",

    # healthcare
    "UNH","LLY","JNJ","PFE","MRK","ABBV",

    # retail
    "WMT","COST","TGT","HD","LOW","DG","ROST",

    # consumer
    "NKE","SBUX","MCD","DIS",

    # enterprise
    "ADBE","ORCL","CRM","IBM"
]


# ---------------- REAL TRADING SCORING ENGINE ----------------
def score_stock(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d")

        if hist is None or hist.empty or len(hist) < 3:
            return 5, "NO DATA", ["Not enough market data"]

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        price = close.iloc[-1]
        prev = close.iloc[-2] if len(close) > 1 else price

        change = (price - prev) / prev if prev != 0 else 0

        vol_avg = volume.mean() if len(volume) > 0 else 1
        vol_now = volume.iloc[-1] if len(volume) > 0 else vol_avg
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1

        score = 5
        reasons = []

        # ---------------- MOMENTUM ----------------
        if change > 0.04:
            score += 3
            reasons.append("Strong upward momentum")
        elif change > 0.015:
            score += 2
            reasons.append("Positive price movement")
        elif change < -0.04:
            score -= 2
            reasons.append("Strong downward pressure")
        else:
            reasons.append("Neutral short-term movement")

        # ---------------- VOLUME ----------------
        if vol_ratio > 2:
            score += 3
            reasons.append("Heavy volume spike (institutional activity)")
        elif vol_ratio > 1.5:
            score += 2
            reasons.append("Above average volume")
        elif vol_ratio > 1.1:
            score += 1
        else:
            reasons.append("Low trading volume")

        score = max(1, min(score, 10))

        if score >= 8:
            label = "🚀 BREAKOUT"
        elif score >= 6:
            label = "🔥 STRONG"
        elif score >= 4:
            label = "👀 WATCH"
        else:
            label = "❌ WEAK"

        return score, label, reasons

    except:
        return 5, "ERROR", ["Data fetch failed"]


# ---------------- /RATE (FULL ANALYSIS) ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):

    await interaction.response.defer()

    score, label, reasons = score_stock(ticker.upper())

    msg = f"📊 **{ticker.upper()} ANALYSIS**\n"
    msg += f"{label} → {score}/10\n\n"

    msg += "📈 SIGNAL BREAKDOWN:\n"
    for r in reasons:
        msg += f"• {r}\n"

    msg += "\n🧠 INTERPRETATION:\n"

    if score >= 8:
        msg += "Strong bullish momentum + breakout conditions. High trader interest."
    elif score >= 6:
        msg += "Healthy upward structure forming. Momentum present."
    elif score >= 4:
        msg += "Mixed signals. No clear directional dominance."
    else:
        msg += "Weak structure with low conviction and pressure."

    await interaction.followup.send(msg)


# ---------------- /SCAN (MARKET DASHBOARD) ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks:
        sc, label, _ = score_stock(s)
        results.append((s, sc, label))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 **MARKET SCAN (TOP MOVERS)**\n\n"

    for r in results[:12]:
        msg += f"{r[0]} → {r[1]}/10 {r[2]}\n"

    await interaction.followup.send(msg)


# ---------------- /BREAKOUTS ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks:
        sc, label, _ = score_stock(s)
        if sc >= 8:
            results.append((s, sc))

    if not results:
        await interaction.followup.send("No strong breakout signals right now.")
        return

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "🚀 **BREAKOUT WATCHLIST**\n\n"

    for r in results:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.followup.send(msg)


# ---------------- /COMPARE ----------------
@tree.command(name="compare")
async def compare(interaction: discord.Interaction, stock1: str, stock2: str):

    await interaction.response.defer()

    s1, l1, r1 = score_stock(stock1.upper())
    s2, l2, r2 = score_stock(stock2.upper())

    winner = stock1.upper() if s1 > s2 else stock2.upper() if s2 > s1 else "Tie"

    msg = f"📊 **COMPARE MODE**\n\n"
    msg += f"{stock1.upper()} → {s1}/10 {l1}\n"
    msg += f"{stock2.upper()} → {s2}/10 {l2}\n\n"
    msg += f"🏆 Winner: {winner}"

    await interaction.followup.send(msg)


# ---------------- SAFE SYNC FIX ----------------
@client.event
async def on_ready():
    try:
        await tree.sync()
        print("Slash commands synced successfully")
    except Exception as e:
        print("Sync error:", e)

    print("Bot is running - PRO Trading Engine Active")


# ---------------- RUN BOT ----------------
client.run(TOKEN)
