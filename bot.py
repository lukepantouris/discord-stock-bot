import os
import discord
from discord import app_commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1516963264486183053


# =========================
# BOT SETUP (IMPORTANT FIX)
# =========================

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = bot.tree   # 🔥 CRITICAL: DO NOT CREATE A NEW TREE


# =========================
# SAFE SYNC LAYER
# =========================

async def sync_commands():
    guild = discord.Object(id=GUILD_ID)
    try:
        await tree.sync(guild=guild)
        print("SYNC OK")
    except Exception as e:
        print("SYNC FAILED:", e)


# =========================
# LIFECYCLE (FIXED ORDER)
# =========================

@bot.event
async def setup_hook():
    await sync_commands()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# =========================
# COMMANDS (REGISTER FIRST)
# =========================

@tree.command(name="help", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Commands: scan, breakout, rate, scalp")


@tree.command(name="scan", guild=discord.Object(id=GUILD_ID))
async def scan_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("scan working")


@tree.command(name="breakout", guild=discord.Object(id=GUILD_ID))
async def breakout_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("breakout working")


@tree.command(name="rate", guild=discord.Object(id=GUILD_ID))
async def rate_cmd(interaction: discord.Interaction, symbol: str):
    await interaction.response.send_message(f"rate: {symbol}")


@tree.command(name="scalp", guild=discord.Object(id=GUILD_ID))
async def scalp_cmd(interaction: discord.Interaction, symbol: str):
    await interaction.response.send_message(f"scalp: {symbol}")


# =========================
# RUN
# =========================

bot.run(DISCORD_TOKEN)
