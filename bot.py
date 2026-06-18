import discord
from discord import app_commands
import yfinance as yf
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- WATCHLIST (expanded + similar stocks) ----------------
stocks = [
    # big tech / AI
    "NVDA","AMD","INTC","TSM","AVGO",
    "AAPL","MSFT","GOOGL","META","AMZN","NFLX",

    # EV / growth
    "TSLA","RIVN","LCID","NIO","XPEV",

    # fintech / crypto exposure
    "COIN","MSTR","SQ","PYPL","HOOD",

    # momentum / retail trading favorites
    "PLTR","SOFI","RIOT","MARA","DKNG",

    # banking / market core
    "JPM","BAC","WFC","GS","MS",

    # healthcare / defensive
    "UNH","LLY","JNJ","PFE","MRK",

    # retail / consumer
    "WMT","COST","TGT","HD","LOW",

    # travel / lifestyle
    "NKE","SBUX",

    # cloud / SaaS
    "CRWD","SNOW","NET","OKTA","DDOG","ADBE","ORCL"
]


# ---------------- REAL TRADING SCORE ENGINE ----------------
def score_stock(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d")

        if hist is None or hist.empty or len(hist) < 3:
            return 5, "NO DATA", ["Not enough market data"]

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        price = close.iloc[-1]
        prev_price = close.iloc[-2] if len(close) > 1 else price

        change = (price - prev_price) / prev_price if prev_price != 0 else 0

        # volume logic
        vol_avg = volume.mean() if len(volume) > 0 else 1
        vol_now = volume.iloc[-1] if len(volume) > 0 else vol_avg
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1

        # short trend
        high_5 = close.max()

        score = 5
        reasons = []

        # ---------------- MOMENTUM ----------------
        if change > 0.04:
            score += 3
            reasons.append("Strong upward momentum today")
        elif change > 0.015:
            score += 2
            reasons.append("Positive price movement")
        elif change < -0.04:
            score -= 2
            reasons.append("Sharp downward move")
        else:
            reasons.append("Flat/neutral movement")

        # ---------------- BREAKOUT LOGIC ----------------
        if price >= high_5:
            score += 2
            reasons.append("Near short-term breakout high")
        elif price >= high_5 * 0.98:
            score += 1
            reasons.append("Testing resistance levels")

        # ---------------- VOLUME ----------------
        if vol_ratio > 2:
            score += 3
            reasons.append("Very high volume spike (institutional interest)")
        elif vol_ratio > 1.5:
            score += 2
            reasons.append("Above average volume")
        elif vol_ratio > 1.1:
            score += 1
        else:
            reasons.append("Low volume activity")

        score = max(1, min(score, 10))

        # label system
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


# ---------------- /RATE (detailed explanation) ----------------
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
        msg += "Strong momentum with breakout conditions. High short-term trader interest."
    elif score >= 6:
        msg += "Healthy bullish structure. Possible continuation trend forming."
    elif score >= 4:
        msg += "Mixed signals. No clear directional dominance."
    else:
        msg += "Weak structure. Low momentum and low conviction."

    await interaction.followup.send(msg)


# ---------------- /SCAN (market overview) ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks:
        sc, label, _ = score_stock(s)
        results.append((s, sc, label))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 **MARKET SCAN (TOP MOVERS)**\n\n"

    for r in results[:10]:
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
        await interaction.followup.send("No strong breakouts detected.")
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


# ---------------- READY ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("Bot is running - Trading Engine Active")


client.run(TOKEN)
