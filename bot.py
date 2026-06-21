import os
import discord
from discord.ext import commands
import aiohttp
import statistics
import yfinance as yf
import asyncio

# =========================
# CONFIG
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

GUILD_ID = 1516963264486183053
BASE_URL = "https://data.alpaca.markets/v2"

alpaca_enabled = bool(ALPACA_KEY and ALPACA_SECRET)

HEADERS = {}
if alpaca_enabled:
    HEADERS = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }

if not DISCORD_TOKEN:
    raise Exception("Missing DISCORD_TOKEN")

# =========================
# BOT CORE
# =========================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# STATE
# =========================

user_modes = {}
watchlists = {}
price_cache = {}

alert_channels = {}      # guild_id -> channel_id
alert_modes = {}          # user_id -> watchlist/top/both

TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"]

MODES = ["investing", "swing", "day", "scalp"]

# =========================
# MODE SYSTEM
# =========================

def get_mode(uid):
    return user_modes.get(uid, "swing")

def apply_mode(mode, score):
    if mode == "investing":
        return score * 0.85
    if mode == "swing":
        return score
    if mode == "day":
        return score * 1.1
    if mode == "scalp":
        return score * 1.25
    return score

# =========================
# DATA
# =========================

async def fetch_json(session, url, params=None):
    try:
        async with session.get(url, headers=HEADERS, params=params, timeout=6) as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

async def alpaca(session, symbol):
    url = f"{BASE_URL}/stocks/{symbol}/bars"

    data = await fetch_json(session, url, {
        "timeframe": "1Min",
        "limit": 120,
        "feed": "iex"
    })

    if not data:
        return None

    bars = data.get("bars", [])
    if not bars:
        return None

    return (
        [b["c"] for b in bars],
        [b["h"] for b in bars],
        [b["l"] for b in bars],
        [b["v"] for b in bars],
    )

async def yahoo(symbol):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1d", interval="1m")

        if df is None or len(df) < 20:
            return None

        return (
            df["Close"].tolist(),
            df["High"].tolist(),
            df["Low"].tolist(),
            df["Volume"].tolist(),
        )
    except:
        return None

async def get_data(session, symbol):
    data = None

    if alpaca_enabled:
        data = await alpaca(session, symbol)

    if not data:
        data = await yahoo(symbol)

    return data

# =========================
# INDICATORS
# =========================

def indicators(c, h, l, v):
    tp = [(h[i] + l[i] + c[i]) / 3 for i in range(len(c))]
    vwap = sum(tp[i] * v[i] for i in range(len(c))) / sum(v) if sum(v) else c[-1]

    gains, losses = [], []

    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        if d > 0:
            gains.append(d)
        else:
            losses.append(abs(d))

    avg_g = sum(gains[-14:]) / 14 if gains else 0
    avg_l = sum(losses[-14:]) / 14 if losses else 1

    rs = avg_g / avg_l if avg_l else 100
    rsi = 100 - (100 / (1 + rs))

    macd = statistics.mean(c[-12:]) - statistics.mean(c[-26:]) if len(c) >= 26 else 0

    return vwap, rsi, macd

def levels(h, l):
    return min(l[-50:]), max(h[-50:])

def breakout(price, resistance):
    return price > resistance * 0.995

# =========================
# SMART ALERT ENGINE (V7)
# =========================

def smart_signal_strength(c, h, l, v):
    vwap, rsi, macd = indicators(c, h, l, v)
    support, resistance = levels(h, l)

    price = c[-1]

    score = 50

    score += 15 if price > vwap else -15
    score += 10 if rsi > 70 else -10 if rsi < 30 else 0
    score += 15 if macd > 0 else -15

    if breakout(price, resistance):
        score += 20

    return max(0, min(100, score)), vwap, rsi

def volatility_score(c):
    returns = [(c[i] - c[i-1]) / c[i-1] for i in range(1, len(c))]
    return statistics.pstdev(returns) * 100 if len(returns) > 2 else 0

def smart_threshold(volatility):
    if volatility < 0.3:
        return 1.5
    elif volatility < 0.8:
        return 1.2
    else:
        return 0.9

# =========================
# ALERT LOOP (V7)
# =========================

async def alert_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            async with aiohttp.ClientSession() as session:

                # =====================
                # WATCHLIST ALERTS
                # =====================
                for user_id, symbols in watchlists.items():

                    mode = alert_modes.get(user_id, "watchlist")

                    if mode in ["watchlist", "both"]:

                        for symbol in symbols:

                            data = await get_data(session, symbol)
                            if not data:
                                continue

                            c, h, l, v = data
                            price = c[-1]

                            old_price = price_cache.get(symbol)
                            price_cache[symbol] = price

                            if old_price:

                                change = ((price - old_price) / old_price) * 100
                                vol = volatility_score(c)

                                threshold = smart_threshold(vol)

                                if abs(change) >= threshold:

                                    try:
                                        user = await bot.fetch_user(user_id)

                                        await user.send(
                                            f"🚨 WATCH ALERT {symbol}\n"
                                            f"Move: {change:.2f}%\n"
                                            f"Price: {price:.2f}\n"
                                            f"Volatility: {vol:.2f}%"
                                        )
                                    except:
                                        pass

                # =====================
                # TOP PICKS ALERTS
                # =====================

                top_results = []

                for t in TICKERS:

                    data = await get_data(session, t)
                    if not data:
                        continue

                    c, h, l, v = data

                    score, vwap, rsi = smart_signal_strength(c, h, l, v)

                    vol = volatility_score(c)

                    if score >= 75:
                        top_results.append((t, score, vol))

                # sort best setups
                top_results.sort(key=lambda x: x[1], reverse=True)
                top_results = top_results[:3]

                for user_id, mode in alert_modes.items():

                    if mode in ["top", "both"] and top_results:

                        try:
                            channel_id = alert_channels.get(GUILD_ID)
                            if channel_id:
                                channel = bot.get_channel(channel_id)

                                if channel:
                                    msg = "📊 TOP SETUPS\n"

                                    for t, s, v in top_results:
                                        msg += f"{t}: {s:.1f} (vol {v:.2f}%)\n"

                                    await channel.send(msg)

                        except:
                            pass

            await asyncio.sleep(60)

        except Exception as e:
            print("ALERT LOOP ERROR:", e)
            await asyncio.sleep(10)

# =========================
# COMMANDS
# =========================

@bot.tree.command(name="help", description="Commands", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction):
    await interaction.response.send_message(
        "/mode /scan /opportunities /scalp /detail /watch /watchlist /alerts set /alerts mode /top"
    )

@bot.tree.command(name="mode", description="Set mode", guild=discord.Object(id=GUILD_ID))
async def mode_cmd(interaction, mode: str):
    mode = mode.lower()

    if mode not in MODES:
        return await interaction.response.send_message(
            "Modes:\ninvesting\nswing\nday\nscalp"
        )

    user_modes[interaction.user.id] = mode
    await interaction.response.send_message(f"Mode → {mode}")

@bot.tree.command(name="alerts_set", description="Set alert channel", guild=discord.Object(id=GUILD_ID))
async def alerts_set(interaction):
    alert_channels[GUILD_ID] = interaction.channel.id
    await interaction.response.send_message("Alerts channel set!")

@bot.tree.command(name="alerts_mode", description="watchlist/top/both", guild=discord.Object(id=GUILD_ID))
async def alerts_mode(interaction, mode: str):
    mode = mode.lower()

    if mode not in ["watchlist", "top", "both"]:
        return await interaction.response.send_message("watchlist / top / both")

    alert_modes[interaction.user.id] = mode
    await interaction.response.send_message(f"Alert mode → {mode}")

@bot.tree.command(name="scan", description="Market scan", guild=discord.Object(id=GUILD_ID))
async def scan_cmd(interaction):
    await interaction.response.defer()

    mode = get_mode(interaction.user.id)
    results = []

    async with aiohttp.ClientSession() as session:
        for t in TICKERS:
            data = await get_data(session, t)
            if not data:
                continue

            c, h, l, v = data
            score, vwap, rsi = smart_signal_strength(c, h, l, v)

            results.append(f"{t}: {score:.1f}")

    await interaction.followup.send(f"MODE: {mode}\n\n" + "\n".join(results))

@bot.tree.command(name="top", description="Top setups", guild=discord.Object(id=GUILD_ID))
async def top_cmd(interaction):
    await interaction.response.defer()

    results = []

    async with aiohttp.ClientSession() as session:
        for t in TICKERS:
            data = await get_data(session, t)
            if not data:
                continue

            c, h, l, v = data
            score, vwap, rsi = smart_signal_strength(c, h, l, v)

            if score >= 75:
                results.append(f"{t}: {score:.1f}")

    if not results:
        return await interaction.followup.send("No setups")

    await interaction.followup.send("\n".join(results))

@bot.tree.command(name="scalp", description="Quick signal", guild=discord.Object(id=GUILD_ID))
async def scalp_cmd(interaction, symbol: str):
    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        data = await get_data(session, symbol)

    if not data:
        return await interaction.followup.send("No data")

    c, h, l, v = data
    score, vwap, rsi = smart_signal_strength(c, h, l, v)

    await interaction.followup.send(
        f"{symbol}\nScore: {score:.1f}\nVWAP {vwap:.2f}\nRSI {rsi:.1f}"
    )

@bot.tree.command(name="detail", description="Full breakdown", guild=discord.Object(id=GUILD_ID))
async def detail_cmd(interaction, symbol: str):
    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        data = await get_data(session, symbol)

    if not data:
        return await interaction.followup.send("No data")

    c, h, l, v = data
    score, vwap, rsi = smart_signal_strength(c, h, l, v)

    await interaction.followup.send(
        f"{symbol}\nScore: {score:.1f}\nVWAP {vwap:.2f}\nRSI {rsi:.1f}"
    )

@bot.tree.command(name="watch", description="Add alert watch", guild=discord.Object(id=GUILD_ID))
async def watch_cmd(interaction, symbol: str):
    watchlists.setdefault(interaction.user.id, [])

    if symbol not in watchlists[interaction.user.id]:
        watchlists[interaction.user.id].append(symbol)

    await interaction.response.send_message(f"Watching {symbol}")

@bot.tree.command(name="watchlist", description="View watchlist", guild=discord.Object(id=GUILD_ID))
async def watchlist_cmd(interaction):
    items = watchlists.get(interaction.user.id, [])

    if not items:
        return await interaction.response.send_message("Empty watchlist")

    await interaction.response.send_message("\n".join(items))

# =========================
# SYNC
# =========================

@bot.event
async def setup_hook():
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("SYNC OK:", [c.name for c in synced])
    except Exception as e:
        print("SYNC ERROR:", e)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    print("===== GUILDS =====")
    for guild in bot.guilds:
        print(f"{guild.name} | {guild.id}")
    print("==================")

    bot.loop.create_task(alert_loop())

# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
