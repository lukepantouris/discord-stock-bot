import os
import discord
from discord.ext import commands
from discord import app_commands
import yfinance as yf
import json

# =========================
# TOKEN
# =========================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("TOKEN NOT FOUND")
    exit()

# =========================
# MEMORY SYSTEM
# =========================
MEMORY_FILE = "memory.json"

def load_memory():
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)

memory = load_memory()

def get_user(user_id):
    if user_id not in memory:
        memory[user_id] = {
            "watchlist": [],
            "mode": "C",
            "alerts": []
        }
    return memory[user_id]

# =========================
# BOT CLASS (SLASH COMMANDS)
# =========================
class StockBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents)

        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synced")

bot = StockBot()

# =========================
# STOCK ANALYSIS ENGINE
# =========================
def analyze_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="7d")

        if hist.empty:
            return None

        closes = hist["Close"]

        change = ((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0]) * 100
        momentum = (closes.iloc[-1] - closes.iloc[-3]) / closes.iloc[-3] * 100

        score = (change * 2) + (momentum * 1.5)

        if score >= 20:
            label = "🚀 BREAKOUT"
        elif score >= 10:
            label = "🔥 STRONG"
        elif score >= 0:
            label = "👀 NEUTRAL"
        else:
            label = "❌ WEAK"

        return {
            "ticker": ticker.upper(),
            "change": round(change, 2),
            "momentum": round(momentum, 2),
            "score": round(score, 2),
            "label": label
        }

    except:
        return None

# =========================
# SLASH COMMANDS
# =========================

@bot.tree.command(name="status", description="Check bot status")
async def status(interaction: discord.Interaction):
    await interaction.response.send_message("🟢 Bot is online")

# -------------------------

@bot.tree.command(name="rate", description="Analyze a stock")
async def rate(interaction: discord.Interaction, ticker: str):

    data = analyze_stock(ticker)

    if not data:
        await interaction.response.send_message("❌ Stock not found")
        return

    await interaction.response.send_message(
        f"""
📊 **{data['ticker']}**

Signal: {data['label']}
Score: {data['score']}
Change: {data['change']}%
Momentum: {data['momentum']}%
"""
    )

# -------------------------

@bot.tree.command(name="scan", description="Scan market movers")
async def scan(interaction: discord.Interaction):

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

    results = []

    for t in tickers:
        data = analyze_stock(t)
        if data:
            results.append(f"{t}: {data['label']} ({data['score']})")

    await interaction.response.send_message("\n".join(results))

# -------------------------

@bot.tree.command(name="movers", description="Rank top movers")
async def movers(interaction: discord.Interaction):

    tickers = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

    ranked = []

    for t in tickers:
        data = analyze_stock(t)
        if data:
            ranked.append((t, data["score"]))

    ranked.sort(key=lambda x: x[1], reverse=True)

    msg = "📈 TOP MOVERS\n\n"
    for t, s in ranked:
        msg += f"{t}: {round(s,2)}\n"

    await interaction.response.send_message(msg)

# -------------------------

@bot.tree.command(name="watch", description="Add stock to watchlist")
async def watch(interaction: discord.Interaction, ticker: str):

    user = str(interaction.user.id)
    data = get_user(user)

    data["watchlist"].append(ticker.upper())
    save_memory(memory)

    await interaction.response.send_message(f"Added {ticker.upper()} to watchlist")

# -------------------------

@bot.tree.command(name="mylist", description="Show watchlist")
async def mylist(interaction: discord.Interaction):

    user = str(interaction.user.id)
    data = get_user(user)

    await interaction.response.send_message(f"Watchlist: {data['watchlist']}")

# -------------------------

@bot.tree.command(name="setmode", description="Set mode A/B/C")
async def setmode(interaction: discord.Interaction, mode: str):

    user = str(interaction.user.id)
    data = get_user(user)

    if mode.upper() not in ["A", "B", "C"]:
        await interaction.response.send_message("Use A, B, or C")
        return

    data["mode"] = mode.upper()
    save_memory(memory)

    await interaction.response.send_message(f"Mode set to {mode.upper()}")

# =========================
# RUN BOT
# =========================

bot.run(TOKEN)
