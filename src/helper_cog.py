import logging
import json
import time

from update_standings import update as update_s
from update_results import update as update_r

from typing import Literal

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import sqlite3

logger = logging.getLogger("bot.helper")

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

GUILD_ID = config["GUILD_ID"]

ORGS = config["ORGS"]
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

    @app_commands.command(description="Forcibly update standings graphics")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def force_update_standings(self, interaction: discord.Interaction):
        logger.debug(f"/force_update_standings used by {interaction.user.id}")
        await interaction.response.defer()
        tiers = list(TIERS.keys()) + ["Overall"]
        try:
            t1 = time.time()
            await asyncio.to_thread(update_s, tiers)
            logger.info(
                f"Successfully updated standings graphics for {len(tiers)} tiers in {round(time.time() - t1, 3)}s"
            )
            await interaction.followup.send("All standings graphics updated")
        except Exception as e:
            logger.error(f"Failed to update standings graphics: {e}")
            await interaction.followup.send("Failed to update standings graphics")

    @app_commands.command(description="Forcibly update results graphics for a specified week")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def force_update_results(self, interaction: discord.Interaction, week: int):
        logger.debug(f"/force_update_results used by {interaction.user.id}")
        await interaction.response.defer()
        tiers = list(TIERS.keys())
        try:
            t1 = time.time()
            await asyncio.to_thread(update_r, tiers, week)
            logger.info(
                f"Successfully updated results graphics for {len(tiers)} tiers in {round(time.time() - t1, 3)}s"
            )
            await interaction.followup.send(f"All results graphics updated for week {week}")
        except Exception as e:
            logger.error(f"Failed to update results graphics: {e}")
            await interaction.followup.send("Failed to update results graphics")

    @app_commands.command(description="Push data to the stats stack")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def push_to_stats_stack(
        self,
        interaction: discord.Interaction,
        game_id: int,
        replay_id: str = None,
        winning_org: str = None,
        losing_org: str = None,
        start_timestamp: int = None,
        end_timestamp: int = None,
        p_out: str = None,
        alt_platform: Literal["steam", "epic", "ps4", "xbox"] = None,
        alt_platform_id: str = None,
    ):
        logger.debug(f"/push_to_stats_stack used by {interaction.user.id}")

        async with self.bot.pool.acquire() as con:
            try:
                await con.execute(
                    """INSERT INTO stats_stack 
                    VALUES((SELECT IFNULL(MAX(priority) + 1, 0) FROM stats_stack), 
                    ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        game_id,
                        replay_id,
                        start_timestamp,
                        end_timestamp,
                        winning_org,
                        losing_org,
                        p_out,
                        alt_platform,
                        alt_platform_id,
                    ),
                )
                logger.info("Successfully pushed to stats stack")
                await interaction.response.send_message(
                    f"Game id {game_id} successfully pushed to the stack"
                )
            except sqlite3.IntegrityError:
                logger.warning("Unable to push to stats stack due to referential integrity error")
                await interaction.response.send_message("Game id does not exist")

    @app_commands.command(description="Push data to the stats stack")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def push_everything_to_stats_stack(self, interaction: discord.Interaction):
        logger.debug(f"/push_everything_to_stats_stack used by {interaction.user.id}")

        # Add all game ids to the stats stack
        async with self.bot.pool.acquire() as con:
            res = await con.execute("SELECT game_id FROM series_log")
            data = await res.fetchall()

            if data == None:
                await interaction.response.send_message("No series exist to push to the stack")
                return

            data = [d["game_id"] for d in data]

            for game_id in data:
                await con.execute(
                    """INSERT INTO stats_stack 
                    VALUES((SELECT IFNULL(MAX(priority) + 1, 0) FROM stats_stack), ?)""",
                    (game_id,),
                )

            logger.info(f"Successfully pushed {len(data)} game ids to the stats stack")
            await interaction.response.send_message(
                f"Successfully pushed {len(data)} game ids to the stats stack"
            )

    @app_commands.command(description="Delete a replay by replay id")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def delete_replay(
        self,
        interaction: discord.Interaction,
        game_id: int,
        replay_id: str,
    ):
        logger.debug(f"/delete_replay used by {interaction.user.id}")

        url = f"https://ballchasing.com/replay/{replay_id}"

        async with self.bot.pool.acquire() as con:

            res = await con.execute(
                "SELECT game_id, COUNT(*) AS num FROM game_stats WHERE url = ?",
                (url,),
            )
            data = await res.fetchone()

            # Check if there are any replays matching the replay id
            if data["num"] == 0:
                logger.warning(f"Replay id {replay_id} not found")
                await interaction.response.send_message("Replay id not found")
                return
            # Check if the supplied game id matches the stored one
            elif data["game_id"] != game_id:
                logger.warning(f"Supplied game id does not match stored value - failing")
                await interaction.response.send_message(
                    f"This replay is registered under id {data['game_id']}"
                )
                return

            logger.info(f"Deleting replay id {replay_id} and updating replay count")
            res = await con.execute(
                "DELETE FROM game_stats WHERE game_id = ? AND url = ?", (game_id, url)
            )

            # Update the number of replays stored and unpublish series in series log
            await con.execute(
                """UPDATE series_log 
                SET replays_stored = (SELECT COUNT(guid) FROM game_stats WHERE game_id = ?),
                published = 0 WHERE game_id = ?""",
                (game_id, game_id),
            )

            await interaction.response.send_message(f"Successfully deleted {replay_id}")

    @push_to_stats_stack.autocomplete("winning_org")
    @push_to_stats_stack.autocomplete("losing_org")
    async def org_autocomplete(self, interaction: discord.Interaction, current: str):

        choices = []
        matched_orgs = [o for o in ORGS.keys() if o.lower().startswith(current.lower())]
        for org in matched_orgs:
            choices.append(app_commands.Choice(name=org, value=org))

        logger.debug(f"Generated {len(choices)} org choices")
        return choices

    @push_to_stats_stack.autocomplete("p_out")
    async def players_autocomplete(self, interaction: discord.Interaction, current: str):
        async with self.bot.pool.acquire() as con:
            res = await con.execute("SELECT name FROM players")

            data = await res.fetchall()
            players = [player[0] for player in data]

        choices = []
        matched_players = [p for p in players if p.lower().startswith(current.lower())]
        for player in matched_players:
            if len(choices) > 23:
                logger.debug("Truncating autocomplete choices (players)")
                break
            else:
                choices.append(app_commands.Choice(name=player, value=player))

        logger.debug(f"Generated {len(choices)} player choices")
        return choices


async def setup(bot):
    await bot.add_cog(Helper(bot))
