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
    @app_commands.command(description="Ping the reporting cog")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ping_results(self, interaction: discord.Interaction):
        logger.debug(f"/ping_results used by {interaction.user.id}")
        await interaction.response.send_message("Pong!", ephemeral=True)

    # View a players series played
    @app_commands.command(description="View a players series played")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def series_played(self, interaction: discord.Interaction, player: discord.User = None):
        logger.debug(f"/series_played used by {interaction.user.id}")

        # If player is None then the author is the player
        if player == None:
            player = interaction.user

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT id, name, tier, org FROM players WHERE id = ?", (str(player.id),)
            )
            player_info = await res.fetchone()

        if player_info == None:
            logger.warning("Series played failing due to player not found")
            await interaction.response.send_message("Player not found")
            return

        logger.info("Successfully found player in database")

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT COUNT(*) FROM series_log_3v3 WHERE ? IN(wp1, wp2, wp3)",
                (player_info["name"],),
            )
            count_win_3v3 = (await res.fetchone())[0]

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT COUNT(*) FROM series_log_3v3 WHERE ? IN(lp1, lp2, lp3)",
                (player_info["name"],),
            )
            count_loss_3v3 = (await res.fetchone())[0]

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT COUNT(*) FROM series_log_2v2 WHERE ? IN(wp1, wp2)",
                (player_info["name"],),
            )
            count_win_2v2 = (await res.fetchone())[0]

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT COUNT(*) FROM series_log_2v2 WHERE ? IN(lp1, lp2)",
                (player_info["name"],),
            )
            count_loss_2v2 = (await res.fetchone())[0]

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT COUNT(*) FROM series_log_1v1 WHERE wp1 = ?",
                (player_info["name"],),
            )
            count_win_1v1 = (await res.fetchone())[0]

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT COUNT(*) FROM series_log_1v1 WHERE lp1 = ?",
                (player_info["name"],),
            )
            count_loss_1v1 = (await res.fetchone())[0]

        embed = discord.Embed(
            title=f"{player_info['name']}",
            description=f"{player_info['org']} | {player_info['tier']}",
        )
        embed.add_field(name="3v3", value=f"{count_win_3v3}-{count_loss_3v3}", inline=False)
        embed.add_field(name="2v2", value=f"{count_win_2v2}-{count_loss_2v2}", inline=False)
        embed.add_field(name="1v1", value=f"{count_win_1v1}-{count_loss_1v1}", inline=False)

        await interaction.response.send_message(embed=embed)

    # View the standings for a tier
    @app_commands.command(description="View the standings for a tier")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def standings(self, interaction: discord.Interaction, tier: str = None):
        logger.debug(f"/standings used by {interaction.user.id}")

        if tier is None:
            async with self.bot.pool.acquire() as con:
                res = await con.execute(
                    "SELECT tier FROM players WHERE id = ?",
                    (interaction.id,),
                )
                data = await res.fetchone()
                if data is None:
                    await interaction.response.send_message("Tier not found")
                else:
                    tier = data[0]

        if tier not in TIERS:
            await interaction.response.send_message("Tier not found")
            return

        org_points = {org: 0 for org in ORGS.keys()}

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT winning_org FROM series_log_3v3 WHERE tier = ?",
                (tier,),
            )
            data = await res.fetchall()

        for series in data:
            org_points[series["winning_org"]] += POINTS_3v3

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT winning_org FROM series_log_2v2 WHERE tier = ?",
                (tier,),
            )
            data = await res.fetchall()

        for series in data:
            org_points[series["winning_org"]] += POINTS_2v2

        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT winning_org FROM series_log_1v1 WHERE tier = ?",
                (tier,),
            )
            data = await res.fetchall()

        for series in data:
            org_points[series["winning_org"]] += POINTS_1v1

        org_points = {org: round(org_points[org], 1) for org in ORGS.keys()}

        ordered_orgs = {
            k: v for k, v in sorted(org_points.items(), key=lambda item: item[1], reverse=True)
        }

        embed = discord.Embed(title=f"{tier} Standings", color=0x1B68BB)
        position = 1
        for org in ordered_orgs:
            embed.add_field(name=f"{position}.", value=f"{org}:\t{ordered_orgs[org]}", inline=False)
            position += 1

        await interaction.response.send_message(embed=embed)

    @standings.autocomplete("tier")
    async def tier_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        matched_tiers = [t for t in TIERS.keys() if t.lower().startswith(current.lower())]
        for tier in matched_tiers:
            choices.append(app_commands.Choice(name=tier, value=tier))

        logger.debug(f"Generated {len(choices)} tier choices")
        return choices


async def setup(bot):
    await bot.add_cog(Results(bot))
