import logging
from os import listdir
import json
import asqlite

from typing import Literal

import discord
from discord.ext import commands
from discord import app_commands
import asyncio


logger = logging.getLogger("bot.reporting")

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

GUILD_ID = config["GUILD_ID"]
TIERS = config["TIERS"]

ORGS = config["ORGS"]
ORG_GUILD_IDS = [ORGS[org]["guild_id"] for org in ORGS]

# Filled using get_players() and get_subs()
PLAYERS = []
SUBS = []


class Reporting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Run asynchronous setup functions
        bot.loop.create_task(self.async_init())

    async def async_init(self):
        logger.debug("Running asynchronous setup functions")
        await self.get_players()
        await self.get_subs()

    # Query the database for registered players - only done at startup
    async def get_players(self):
        PLAYERS = []
        async with self.bot.pool.acquire() as con:
            res = await con.execute("SELECT id FROM players")
            for row in await res.fetchall():
                PLAYERS.append(row["id"])
        logger.info("Successfully fetched players from database")

    # Query the database for registered subs - done at startup and on /register_sub
    async def get_subs(self):
        SUBS = []
        async with self.bot.pool.acquire() as con:
            res = await con.execute("SELECT id FROM subs")
            for row in await res.fetchall():
                SUBS.append(row["id"])
        logger.info("Successfully fetched subs from database")

    # Ping reporting cog
    @app_commands.command(description="Ping the reporting cog")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ping_reporting(self, interaction: discord.Interaction):
        logger.debug(f"/ping_reporting used by {interaction.user.id}")
        await interaction.response.send_message("Pong!", ephemeral=True)

    # Record a new sub entry in the database
    @app_commands.command(description="Register a new sub")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def register_sub(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        name: str,
        platform: str,
        platform_id: str,
    ):
        logger.debug(f"/register_sub used by {interaction.user.id}")
        async with self.bot.pool.acquire() as con:
            await con.execute(
                "INSERT INTO subs VALUES(?, ?, ?, ?)", (user.id, name, platform, platform_id)
            )

        # Update the list of subs
        await self.get_subs()

        logger.info(f"Registered {name} as a sub")

        await interaction.response.send_message(f"{name} has been registered as a sub")

    @app_commands.command(description="Report a 3v3 result")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def report_3v3(
        self,
        interaction: discord.Interaction,
        tier: str,
        winning_org: str,
        losing_org: str,
        score: Literal["3-0", "3-1", "3-2"],
        played_previously: int = 0,
        wp1: discord.User = None,
        wp2: discord.User = None,
        wp3: discord.User = None,
        lp1: discord.User = None,
        lp2: discord.User = None,
        lp3: discord.User = None,
    ):
        logger.debug(f"/report_3v3 used by {interaction.user.id}")

        if tier not in TIERS.keys():
            logger.warning("Report failing due to invalid tier argument")
            await interaction.response.send_message("Invalid tier argument supplied")
            return
        if winning_org not in ORGS.keys() or losing_org not in ORGS.keys():
            logger.warning("Report failing due to invalid org argument")
            await interaction.response.send_message("Invalid org argument supplied")
            return
        if winning_org == losing_org:
            logger.warning("Report failing due to duplicate org arguments")
            await interaction.response.send_message(
                "The winning org and losing org cannot be the same"
            )
            return
        if played_previously < 0:
            logger.warning("Report failing due to invalid played previously argument")
            await interaction.response.send_message(
                "The played_previously argument cannot be less than 0"
            )
            return

        # Store non None user objects of players
        winning_players = [p.id for p in [wp1, wp2, wp3] if p is not None]
        losing_players = [p for p in [lp1, lp2, lp3] if p is not None]

        if len(winning_players) + len(losing_players) not in [0, 6]:
            logger.warning("Report failing due to incorrect number of player arguments")
            await interaction.response.send_message(
                "You must supply either 0 or 6 player arguments"
            )
            return

        # Query the database to get the players assumed to be in the match
        # If no players are supplied, those are the players
        # If all players have been specified, ensure they are either one of the assumed players,
        # or are a registered sub

        await interaction.response.send_message("Echo")

    @report_3v3.autocomplete("winning_org")
    @report_3v3.autocomplete("losing_org")
    async def org_autocomplete(self, interaction: discord.Interaction, current: str):

        choices = []
        matched_orgs = [org for org in ORGS.keys() if org.lower().startswith(current.lower())]
        for org in matched_orgs:
            choices.append(app_commands.Choice(name=org, value=org))

        logger.debug(f"Generated {len(choices)} org choices")
        return choices

    @report_3v3.autocomplete("tier")
    async def tier_autocompelte(self, interaction: discord.Interaction, current: str):
        choices = []
        matched_tiers = [tier for tier in TIERS.keys() if tier.lower().startswith(current.lower())]
        for tier in matched_tiers:
            choices.append(app_commands.Choice(name=tier, value=tier))

        logger.debug(f"Generated {len(choices)} tier choices")
        return choices


async def setup(bot):
    await bot.add_cog(Reporting(bot))
