import discord
from discord import app_commands
import yfinance as yf
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- WATCHLIST ----------------
stocks = [
    "NVDA","AMD","PLTR","TSLA","SOFI","AAPL",
    "MSFT","GOOGL","META","AMZN","NFLX",
    "AVGO","MU","QCOM","INTC",
    "RIVN","LCID","NIO",
    "JPM","BAC","WFC","GS","MS",
    "UNH","LLY","JNJ","PFE","MRK",
    "WMT","COST","TGT","HD","LOW",
    "NKE","SBUX",
    "COIN","MSTR","RIOT","MARA","HOOD",
    "SHOP","SQ","PYPL","ROKU","SPOT",
    "CRWD","SNOW","NET","OKTA","DDOG",
    "ADBE","ORCL"
]

# ---------------- REAL SCORING ENGINE ----------------
def score_stock(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="3mo")

        if hist is None or hist.empty or len(hist) < 20:
            return 3, "NO DATA"

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        price = close.iloc[-1]

        # trend
        sma10 = close.rolling(10).mean().dropna()
        sma20 = close.rolling(20).mean().dropna()

        sma_fast = sma10.iloc[-1] if len(sma10) else price
        sma_slow = sma20.iloc[-1] if len(sma20) else price

        # momentum
        high_10 = close.iloc[-10:].max()
        high_20 = close.iloc[-20:].max()

        # volume pressure
        vol_avg = volume.rolling(10).mean().dropna()
        vol_ratio = 1

        if len(vol_avg):
            vol_ratio = volume.iloc[-1] / vol_avg.iloc[-1]

        score = 0
        reasons = []

        # ---------------- TREND ----------------
        if price > sma_fast:
            score += 2
            reasons.append("Above short-term trend")
        if price > sma_slow:
            score += 2
            reasons.append("Above mid trend")

        # ---------------- MOMENTUM ----------------
        if price >= high_10:
            score += 3
            reasons.append("Near breakout (10-day high)")
        elif price >= high_20:
            score += 2
            reasons.append("Strong momentum")

        # ---------------- VOLUME ----------------
        if vol_ratio > 2:
            score += 3
            reasons.append("High volume spike")
        elif vol_ratio > 1.5:
            score += 2
            reasons.append("Above average volume")
        elif vol_ratio > 1.1:
            score += 1

        score = min(score, 10)

        # label
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
        return 3, "ERROR", ["Data unavailable"]


# ---------------- /RATE ----------------
@tree.command(name="rate")
async def rate(interaction: discord.Interaction, ticker: str):

    await interaction.response.defer()

    t = ticker.upper()
    s, label, reasons = score_stock(t)

    msg = f"📊 {t}\n{label} → {s}/10\n\n"

    for r in reasons[:4]:
        msg += f"• {r}\n"

    await interaction.followup.send(msg)


# ---------------- /SCAN ----------------
@tree.command(name="scan")
async def scan(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks:
        score, label, reasons = score_stock(s)
        results.append((s, score, label, reasons))

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 MARKET SCAN\n\n"

    for r in results[:10]:
        msg += f"{r[0]} → {r[1]}/10 {r[2]}\n"

    await interaction.followup.send(msg)


# ---------------- /BREAKOUTS ----------------
@tree.command(name="breakouts")
async def breakouts(interaction: discord.Interaction):

    await interaction.response.defer()

    results = []

    for s in stocks:
        score, label, reasons = score_stock(s)
        if score >= 8:
            results.append((s, score))

    if not results:
        await interaction.followup.send("No breakouts right now.")
        return

    results.sort(key=lambda x: x[1], reverse=True)

    msg = "🚀 BREAKOUT LIST\n\n"

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

    msg = f"{stock1.upper()} → {s1}/10 {l1}\n"
    msg += f"{stock2.upper()} → {s2}/10 {l2}\n\n"
    msg += f"Winner: {winner}"

    await interaction.followup.send(msg)


# ---------------- READY ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("Bot is running")


client.run(TOKEN)
