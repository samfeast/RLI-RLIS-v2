import logging

import discord
from discord.ext import commands
import asyncio
from os import listdir
import time
import csv
import json

logger = logging.getLogger("bot.main")

# Suppress shard related logs from discord.gateway
logging.getLogger("discord.gateway").setLevel(30)

logging.basicConfig(
    filename="../logs/dpy.log",
    encoding="utf-8",
    datefmt="%Y-%m-%d %H:%M:%S",
    format="[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    level=logging.DEBUG,
)

logger.debug(f"Starting logger")


with open("../config.json", "r") as read_file:
    config = json.load(read_file)

TOKEN = config["TOKEN"]
GUILD_ID = config["GUILD_ID"]
PREFIX = config["PREFIX"]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class RLIS_Bot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def setup_hook(self):
        # Attempt to load each cog in turn
        cogs = [f[:-3] for f in listdir() if "cog" == f[-6:-3]]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Successfully loaded {cog} cog")
            except Exception as e:
                logger.error(f"Failed to load {cog} cog ({type(e).__name__}: {e})")


# Create bot instance and initialise slash command tree
bot = RLIS_Bot(command_prefix=PREFIX, intents=intents)
tree = bot.tree

# Event called after login is successful
@bot.event
async def on_ready():
    logger.info(f"Successfully logged in as {bot.user.name}, present in {len(bot.guilds)} guilds")
    logger.debug(f"Successfully logged in as {bot.user.id}")
    for guild in bot.guilds:
        logger.debug(f"Bot present in guild {guild.name} ({guild.id})")

    print("Connected.")


# Sync all slash commands in current guild
# Only required when a new command is added, or a command declaration is changed
@bot.command()
async def synclocal_rlis(ctx):
    logger.debug(f"/synclocal_rlis used by {ctx.author.id}")
    await tree.sync(guild=ctx.guild)
    logger.info(f"Command tree synced in guild {ctx.guild.name} ({ctx.guild.id})")
    await ctx.send("Slash commands synced.")


# Reload a cog (cog argument need not contain _cog.py)
@bot.command()
async def reload_rlis(ctx, cog):
    logger.debug(f"/reload_rlis used by {ctx.author.id}")
    try:
        await bot.reload_extension(f"{cog.lower()}_cog")
        logger.info(f"Successfully reloaded {cog.lower()} cog")
        await ctx.send(f"{cog.lower()}_cog reloaded successfully.")
    except Exception as e:
        logger.error(f"Failed to reload {cog} cog ({type(e).__name__}: {e})")
        await ctx.send(f"Failed to reload {cog.lower()}_cog.")


# Reload all cogs
@bot.command()
async def reload_all_rlis(ctx):
    logger.debug(f"/reload_all_rlis used by {ctx.author.id}")
    cogs = {f[:-3] for f in listdir() if "cog" == f[-6:-3]}
    failed_cogs = set()
    for cog in cogs:
        try:
            await bot.reload_extension(cog)
            logger.info(f"Successfully reloaded {cog} cog")
        except Exception as e:
            logger.error(f"Failed to reload {cog} cog ({type(e).__name__}: {e})")
            failed_cogs.add(cog)

    if len(cogs) > 0:
        await ctx.send(f"Successfully reloaded cogs:\n\t{",".join(cogs - failed_cogs)}")
        if len(failed_cogs) > 0:
            await ctx.send(f"Failed to reloaded cogs:\n\t{",".join(failed_cogs)}")
    else:
        await ctx.send(f"No cogs to reload.")


# Ping bot using prefix command
@bot.command()
async def ping_rlis(ctx):
    logger.debug(f"/ping_rlis used by {ctx.author.id}")
    await ctx.send("Pong!")

# Ping main cog using slash command
@tree.command(description="Ping main cog.", guild=discord.Object(id=GUILD_ID))
async def ping_main(interaction: discord.Interaction):
    logger.debug(f"/reload_rlis used by {interaction.user.id}")
    await interaction.response.send_message("Pong!", ephemeral=True)


# Start bot
async def main():
    logger.debug("Attempting to launch bot")
    await bot.start(TOKEN)


asyncio.run(main())
