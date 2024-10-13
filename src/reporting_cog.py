import logging
from os import listdir
import json
import asqlite

import discord
from discord.ext import commands
from discord import app_commands
import asyncio


logger = logging.getLogger("bot.reporting")

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

GUILD_ID = config["GUILD_ID"]


class Reporting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Ping reporting cog
    @app_commands.command(description="Ping the reporting cog")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ping_reporting(self, interaction: discord.Interaction):
        logger.debug(f"/ping_reporting used by {interaction.user.id}")
        await interaction.response.send_message("Pong!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Reporting(bot))
