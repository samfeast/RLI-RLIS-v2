import logging
import json
import time

from update_standings import update

import discord
from discord.ext import commands
from discord import app_commands
import asyncio

logger = logging.getLogger("bot.helper")

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

GUILD_ID = config["GUILD_ID"]

TIERS = config["TIERS"]


class Helper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Ping helper cog
    @app_commands.command(description="Ping the helper cog")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ping_helper(self, interaction: discord.Interaction):
        logger.debug(f"/ping_helper used by {interaction.user.id}")
        await interaction.response.send_message("Pong!", ephemeral=True)

    @app_commands.command(description="Ping the helper cog")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def force_update_standings(self, interaction: discord.Interaction):
        logger.info("Attempting to update standings graphics")
        await interaction.response.defer()
        tiers = list(TIERS.keys()) + ["Overall"]
        try:
            t1 = time.time()
            await asyncio.to_thread(update, tiers)
            logger.info(
                f"Successfully updated standings graphics for {len(tiers)} tiers in {round(time.time() - t1, 3)}s"
            )
            await interaction.followup.send("All standings graphics updated")
        except Exception as e:
            logger.error(f"Failed to update standings graphics: {e}")
            await interaction.followup.send("Failed to update standings graphics")


async def setup(bot):
    await bot.add_cog(Helper(bot))