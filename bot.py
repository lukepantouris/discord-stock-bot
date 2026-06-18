import discord
from discord import app_commands
import yfinance as yf
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------------- STOCK LIST ----------------
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

# ---------------- SAFE SCORE SYSTEM ----------------
def score(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="6mo")

        # safety checks (CRITICAL FIX)
        if hist is None or hist.empty or len(hist) < 60:
            return 0

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        if len(close) < 20 or len(volume) < 20:
            return 0

        price = close.iloc[-1]

        sma50_series = close.rolling(50).mean().dropna()
        if sma50_series.empty:
            return 0
        sma50 = sma50_series.iloc[-1]

        vol_avg_series = volume.rolling(20).mean().dropna()
        if vol_avg_series.empty:
            return 0
        vol_avg = vol_avg_series.iloc[-1]

        vol_now = volume.iloc[-1]
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 0

        last_10_high = close.iloc[-10:].max()

        score = 0

        # Trend
        if price > sma50:
            score += 3

        # Momentum
        if price >= last_10_high:
            score += 3

        # Volume spike
        if vol_ratio > 2:
            score += 3
        elif vol_ratio > 1.5:
            score += 2
        elif vol_ratio > 1.2:
            score += 1

        return min(score, 10)

    except:
        return 0


# ---------------- /RATE ----------------
@tree.command(name="rate", description="Rate a stock")
async def rate(interaction: discord.Interaction, ticker: str):
    t = ticker.upper()

    s = score(t)

    if s >= 8:
        label = "🚀 BREAKOUT"
    elif s >= 6:
        label = "🔥 STRONG"
    elif s >= 4:
        label = "👀 WATCH"
    else:
        label = "❌ WEAK"

    await interaction.response.send_message(f"{t} → {s}/10 ({label})")


# ---------------- /SCAN ----------------
@tree.command(name="scan", description="Scan stocks")
async def scan(interaction: discord.Interaction):

    results = [(s, score(s)) for s in stocks]
    results.sort(key=lambda x: x[1], reverse=True)

    msg = "📊 TOP STOCKS\n\n"

    for r in results[:7]:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.response.send_message(msg)


# ---------------- /BREAKOUTS ----------------
@tree.command(name="breakouts", description="Only breakout stocks")
async def breakouts(interaction: discord.Interaction):

    results = [(s, score(s)) for s in stocks]
    results = [r for r in results if r[1] >= 8]
    results.sort(key=lambda x: x[1], reverse=True)

    if not results:
        await interaction.response.send_message("No breakouts right now.")
        return

    msg = "🚀 BREAKOUTS\n\n"

    for r in results:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.response.send_message(msg)


# ---------------- /COMPARE ----------------
@tree.command(name="compare", description="Compare stocks")
async def compare(interaction: discord.Interaction, stock1: str, stock2: str):

    s1 = stock1.upper()
    s2 = stock2.upper()

    sc1 = score(s1)
    sc2 = score(s2)

    winner = s1 if sc1 > sc2 else s2 if sc2 > sc1 else "Tie"

    msg = f"📊 {s1} vs {s2}\n\n"
    msg += f"{s1}: {sc1}/10\n"
    msg += f"{s2}: {sc2}/10\n\n"
    msg += f"Winner: {winner}"

    await interaction.response.send_message(msg)


# ---------------- MOMENTUM ----------------
@tree.command(name="momentum", description="Fast movers")
async def momentum(interaction: discord.Interaction):

    results = [(s, score(s)) for s in stocks]
    results.sort(key=lambda x: x[1], reverse=True)

    msg = "⚡ MOMENTUM\n\n"

    for r in results[:5]:
        msg += f"{r[0]} → {r[1]}/10\n"

    await interaction.response.send_message(msg)


# ---------------- BOT START ----------------
@client.event
async def on_ready():
    await tree.sync()
    print("Bot is running")


client.run(TOKEN)
