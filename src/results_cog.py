import logging
from os import listdir
import json

import discord
from discord.ext import commands
from discord import app_commands


logger = logging.getLogger("bot.results")

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

GUILD_ID = config["GUILD_ID"]

POINTS_3v3 = config["POINTS_3v3"]
POINTS_2v2 = config["POINTS_2v2"]
POINTS_1v1 = config["POINTS_1v1"]

TIERS = config["TIERS"]

ORGS = config["ORGS"]


class Results(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Ping results cog
    @app_commands.command(description="Ping the results cog")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ping_results(self, interaction: discord.Interaction):
        logger.debug(f"/ping_results used by {interaction.user.id}")
        await interaction.response.send_message("Pong!", ephemeral=True)

    # View a players series played
    @app_commands.command(description="View a players series record")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def series_played(self, interaction: discord.Interaction, player: discord.User = None):
        logger.debug(f"/series_played used by {interaction.user.id}")

        # If player is None then the author is the player
        if player == None:
            player = interaction.user

        # Get the tier and org of the necessary player
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT name, tier, org FROM players WHERE id = ?", (player.id,)
            )

            player_info = await res.fetchone()

        if player_info == None:
            logger.warning("/series_played failing as player does not exist")
            await interaction.response.send_message("Player not found", ephemeral=True)
            return

        logger.info("Successfully found player in database")

        # Get the number of 3s series wins and losses
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                """SELECT 
                    SUM(CASE WHEN ? IN(wp1, wp2, wp3) THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN ? IN(lp1, lp2, lp3) THEN 1 ELSE 0 END) AS losses
                FROM series_log_3v3""",
                (player_info["name"], player_info["name"]),
            )
            data = await res.fetchone()
            record_3v3 = f"{data[0]}-{data[1]}"

        # Get the number of 2s series wins and losses
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                """SELECT 
                    SUM(CASE WHEN ? IN(wp1, wp2) THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN ? IN(lp1, lp2) THEN 1 ELSE 0 END) AS losses
                FROM series_log_2v2""",
                (player_info["name"], player_info["name"]),
            )
            data = await res.fetchone()
            record_2v2 = f"{data[0]}-{data[1]}"

        # Get the number of 1s series wins and losses
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                """SELECT 
                    SUM(CASE WHEN wp1 = ? THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN lp1 = ? THEN 1 ELSE 0 END) AS losses
                FROM series_log_1v1""",
                (player_info["name"], player_info["name"]),
            )
            data = await res.fetchone()
            record_1v1 = f"{data[0]}-{data[1]}"

        # Send the embed with the org logo as the thumbnail
        logo_file = ORGS[player_info["org"]]["logo_file"]
        f = discord.File(f"./assets/logos/{logo_file}", filename="image.png")
        embed = discord.Embed(
            title=f"{player_info['name']}",
            description=f"**{player_info['org']} — {player_info['tier']}**",
            colour=discord.Colour.from_str(ORGS[player_info["org"]]["colour"]),
        )
        embed.set_thumbnail(url="attachment://image.png")
        embed.add_field(name="3v3", value=record_3v3, inline=True)
        embed.add_field(name="2v2", value=record_2v2, inline=True)
        embed.add_field(name="1v1", value=record_1v1, inline=True)

        await interaction.response.send_message(file=f, embed=embed)

    # View the standings for a tier
    @app_commands.command(description="View the standings for a specified tier")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def standings(self, interaction: discord.Interaction, tier: str = None):
        logger.debug(f"/standings used by {interaction.user.id}")

        if tier is None:
            async with self.bot.pool.acquire() as con:
                res = await con.execute(
                    "SELECT tier FROM players WHERE id = ?",
                    (interaction.user.id,),
                )
                data = await res.fetchone()
                if data is None:
                    logger.warning(
                        f"/standings failing as no tier was supplied by a non playing user"
                    )
                    await interaction.response.send_message("Tier not found")
                    return
                else:
                    tier = data[0]

        f = discord.File(
            f"../data/graphics/{tier.replace(' ', '_').lower()}.png", filename="image.png"
        )
        logger.debug("Ready to send image")
        await interaction.response.send_message(file=f)

    # View the results for a tier
    @app_commands.command(description="View the results for a specified tier in a particular week")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def results(self, interaction: discord.Interaction, week: int, tier: str = None):
        logger.debug(f"/results used by {interaction.user.id}")

        if tier is None:
            async with self.bot.pool.acquire() as con:
                res = await con.execute(
                    "SELECT tier FROM players WHERE id = ?",
                    (interaction.user.id,),
                )
                data = await res.fetchone()
                if data is None:
                    logger.warning(
                        f"/results failing as no tier was supplied by a non playing user"
                    )
                    await interaction.response.send_message("Tier not found")
                    return
                else:
                    tier = data[0]
        try:
            f = discord.File(
                f"../data/graphics/{tier.replace(' ', '_').lower()}_week_{week}.png",
                filename="image.png",
            )
            logger.debug("Ready to send image")
            await interaction.response.send_message(file=f)
        except FileNotFoundError:
            logger.debug("Failed to send image as the required graphic does not exist")
            await interaction.response.send_message("No results to show")

    @standings.autocomplete("tier")
    async def tier_autocomplete_with_overall(self, interaction: discord.Interaction, current: str):
        choices = []
        matched_tiers = [
            t for t in list(TIERS.keys()) + ["Overall"] if t.lower().startswith(current.lower())
        ]
        for tier in matched_tiers:
            choices.append(app_commands.Choice(name=tier, value=tier))

        logger.debug(f"Generated {len(choices)} tier choices")
        return choices

    @results.autocomplete("tier")
    async def tier_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        matched_tiers = [t for t in list(TIERS.keys()) if t.lower().startswith(current.lower())]
        for tier in matched_tiers:
            choices.append(app_commands.Choice(name=tier, value=tier))

        logger.debug(f"Generated {len(choices)} tier choices")
        return choices


async def setup(bot):
    await bot.add_cog(Results(bot))
