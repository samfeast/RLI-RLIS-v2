import logging
import json
import time


import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio

logger = logging.getLogger("bot.tasks")

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

GUILD_ID = config["GUILD_ID"]
STAT_CHANNEL_ID = config["STAT_CHANNEL_ID"]

MAX_GAMES_3v3 = config["MAX_GAMES_3v3"]
MAX_GAMES_2v2 = config["MAX_GAMES_2v2"]
MAX_GAMES_1v1 = config["MAX_GAMES_1v1"]


class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.publish_stats.start()

    # Ping helper cog
    @app_commands.command(description="Ping the tasks cog")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ping_tasks(self, interaction: discord.Interaction):
        logger.debug(f"/ping_tasks used by {interaction.user.id}")
        await interaction.response.send_message("Pong!", ephemeral=True)

    @tasks.loop(minutes=1)
    async def publish_stats(self):
        channel = self.bot.get_channel(STAT_CHANNEL_ID)
        # Get the data of the oldest series which has not been published,
        # but replays have been search for
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                """SELECT L.game_id, L.tier, 
                L.winning_org, L.losing_org, L.mode, L.games_won_by_loser, 
                P.wp1, P.wp2, P.wp3, P.lp1, P.lp2, P.lp3 
                FROM series_log AS L JOIN series_players AS P ON L.game_id = P.game_id 
                WHERE published = 0 AND replays_stored IS NOT NULL 
                ORDER BY timestamp ASC LIMIT 1"""
            )

        d = await res.fetchone()

        # If d is None, there are no unpublished series, so do nothing
        if d is not None:
            game_id = d["game_id"]

            logger.info(f"Running publish stats task on game id {game_id}")

            # Get the winning and losing players
            winning_players = [p for p in [d["wp1"], d["wp2"], d["wp3"]] if p is not None]
            losing_players = [p for p in [d["lp1"], d["lp2"], d["lp3"]] if p is not None]

            if d["mode"] == 3:
                max_games = MAX_GAMES_3v3
            if d["mode"] == 2:
                max_games = MAX_GAMES_2v2
            if d["mode"] == 1:
                max_games = MAX_GAMES_1v1

            # Get the replay urls from the game_stats table for the series
            async with self.bot.pool.acquire() as con:
                res = await con.execute(
                    "SELECT url FROM game_stats WHERE game_id = ? ORDER BY timestamp ASC",
                    (game_id,),
                )

            series_urls = await res.fetchall()

            # Format the urls for the embed
            urls_fmt = []
            for i in range(len(series_urls)):
                urls_fmt.append(f"[Game {i+1}]({series_urls[i]['url']})")

            # Colour the embed based on the extent of replays found
            if len(series_urls) == 0:
                logger.debug(f"Publishing {game_id} with no replays found")
                embed_colour = 0xCC3232
            elif len(series_urls) == max_games + d["games_won_by_loser"]:
                logger.debug(f"Publishing {game_id} with all replays found")
                embed_colour = 0x2DC937
            else:
                logger.debug(f"Publishing {game_id} with some replays found")
                embed_colour = 0xDB7B2B

            embed = discord.Embed(
                title=f"{d['winning_org']} vs {d['losing_org']} — ({max_games} - {d['games_won_by_loser']})",
                colour=embed_colour,
            )
            embed.add_field(
                name=f"{d['tier']} {d['mode']}v{d['mode']}",
                value=f"{', '.join(winning_players)} vs {', '.join(losing_players)}",
                inline=False,
            )
            embed.add_field(
                name=f"{len(series_urls)}/{max_games + d['games_won_by_loser']} replays found",
                value="",
                inline=False,
            )
            embed.add_field(name="Links:", value=", ".join(urls_fmt), inline=False)
            embed.set_footer(text=f"Think this is wrong? Ask Res (id: {game_id})")

            try:
                f = discord.File(
                    f"../data/graphics/{game_id}.png",
                    filename="image.png",
                )
                logger.debug("Ready to send image")
                await channel.send(file=f, embed=embed)
            except FileNotFoundError:
                logger.debug("No stat graphic available, sending without it")
                await channel.send(embed=embed)

            # Set the game id as published
            async with self.bot.pool.acquire() as con:
                await con.execute(
                    "UPDATE series_log SET published = 1 WHERE game_id = ?", (game_id,)
                )

            logger.info(f"{game_id} has been published")

    @publish_stats.before_loop
    async def before_publish_stats(self):
        logger.debug("Publish stats task loop waiting for bot startup")
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Tasks(bot))
