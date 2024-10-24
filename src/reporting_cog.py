import logging
import json
import time

from typing import Literal

from update_standings import update as update_s
from update_results import update as update_r

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


class Reporting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.PLAYERS = []
        self.SUBS = []

    # Query the database for registered players - done on first use of /report_...
    async def get_players(self):
        self.PLAYERS = []
        async with self.bot.pool.acquire() as con:
            res = await con.execute("SELECT name FROM players WHERE status = 'main'")
            for row in await res.fetchall():
                self.PLAYERS.append(row["name"])

        logger.info("Successfully fetched players from database")

    # Query the database for registered subs - done on first use of /report_...
    async def get_subs(self):
        self.SUBS = []
        async with self.bot.pool.acquire() as con:
            res = await con.execute("SELECT name FROM players WHERE status = 'sub'")
            for row in await res.fetchall():
                self.SUBS.append(row["name"])
        logger.info("Successfully fetched subs from database")

    async def generate_game_id(self, org1, org2, tier, mode):
        org1_id = ORGS[org1]["id"]
        org2_id = ORGS[org2]["id"]
        tier_id = TIERS[tier]

        return f"{max(org1_id, org2_id)}{min(org1_id, org2_id)}{tier_id}{mode}"

    async def validate_report_args(
        self,
        tier,
        winning_org,
        losing_org,
        played_previously,
        winning_players,
        losing_players,
        mode,
    ):
        game_id = await self.generate_game_id(winning_org, losing_org, tier, mode)

        # Check that the tier exists
        if tier not in TIERS.keys():
            logger.warning("Report failing due to invalid tier argument")
            return "Invalid tier argument supplied"

        # Check that both orgs exist
        if winning_org not in ORGS.keys() or losing_org not in ORGS.keys():
            logger.warning("Report failing due to invalid org argument")
            return "Invalid org argument supplied"

        # Check that the orgs are different
        if winning_org == losing_org:
            logger.warning("Report failing due to duplicate org arguments")
            return "The winning org and losing org cannot be the same"

        # Check that played_previously is not negative
        if played_previously < 0:
            logger.warning("Report failing due to invalid played previously argument")
            return "The played_previously argument cannot be less than 0"

        # Check that the number of players entered is either 0 or 6 if the mode is 3v3
        if mode == 3 and len(winning_players) + len(losing_players) not in [0, 6]:
            logger.warning("Report failing due to incorrect number of player arguments")
            return "You must supply either 0 or 6 player arguments"

        # Get the players who could have played from the main rosters
        expected_winning_players = []
        expected_losing_players = []
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                "SELECT name, org FROM players WHERE tier = ? AND (org = ? OR org = ?) AND status = 'main'",
                (tier, winning_org, losing_org),
            )
            for row in await res.fetchall():
                if row[1] == winning_org:
                    expected_winning_players.append(row[0])
                else:
                    expected_losing_players.append(row[0])

        # Check that all entries are either expected, or registered subs
        for player in winning_players:
            if player not in expected_winning_players and player not in self.SUBS:
                logger.warning("Report failing due to invalid player argument")
                return (
                    "At least one player argument is invalid (Did you forget to register a sub?)"
                )
        for player in losing_players:
            if player not in expected_losing_players and player not in self.SUBS:
                logger.warning("Report failing due to invalid player argument")
                return (
                    "At least one player argument is invalid (Did you forget to register a sub?)"
                )

        return None

    # Generate a discord.Embed object to display a result from a Series_Result
    async def generate_report_embed(self, res):
        if res.mode == 3:
            mode_str = "3v3"
        elif res.mode == 2:
            mode_str = "2v2"
        elif res.mode == 1:
            mode_str = "1v1"

        embed = discord.Embed(title=res.game_id, color=0x1B68BB)
        embed.add_field(name="Tier", value=res.tier, inline=True)
        embed.add_field(name="Gamemode", value=mode_str, inline=True)
        embed.add_field(name="Played...day(s) ago", value=res.played_previously, inline=True)
        embed.add_field(name="Winner", value=res.winning_org, inline=True)
        embed.add_field(name="Loser", value=res.losing_org, inline=True)
        embed.add_field(name="Score", value=res.score, inline=True)
        embed.add_field(name="Winning Players", value=", ".join(res.winning_players), inline=True)
        embed.add_field(name="Losing Players", value=", ".join(res.losing_players), inline=True)
        embed.set_footer(text="If this is incorrect, message Res.")

        logger.info(f"Generated report embed for game id {res.game_id}")

        return embed

    # Store a Series_Result in the db
    async def store_series_result(self, res):

        # Pad winning and losing player lists to make them fit in the same query for all modes
        winning_players = res.winning_players + ([None] * (6 - len(res.winning_players)))
        losing_players = res.losing_players + ([None] * (6 - len(res.winning_players)))

        # Write to the series_log table, then to series_players
        # This is needed to maintain referential integrity
        async with self.bot.pool.acquire() as con:
            await con.execute(
                """INSERT INTO series_log
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    round(time.time()),
                    res.game_id,
                    res.tier,
                    res.mode,
                    res.winning_org,
                    res.losing_org,
                    int(res.score[-1]),
                    res.played_previously,
                    None,
                    0,
                ),
            )
            await con.execute(
                """INSERT INTO series_players
                VALUES(?, ?, ?, ?, ?, ?, ?)""",
                (
                    res.game_id,
                    winning_players[0],
                    winning_players[1],
                    winning_players[2],
                    losing_players[0],
                    losing_players[1],
                    losing_players[2],
                ),
            )

            # Push entry onto stats_stack such that the priority exceeds all present entries
            await con.execute(
                """INSERT INTO stats_stack(priority, game_id) 
                VALUES (
                (SELECT IFNULL(MAX(priority) + 1, 0) FROM stats_stack), 
                ?)""",
                (res.game_id,),
            )

    # Update standings graphics by calling the relevant synchronous function in another thread
    async def update_standings_graphics(self, tiers):
        logger.info("Attempting to update standings graphics")
        try:
            t1 = time.time()
            await asyncio.to_thread(update_s, tiers)
            logger.info(
                f"Successfully updated standings graphics for {len(tiers)} tiers in {round(time.time() - t1, 3)}s"
            )
        except Exception as e:
            logger.error(f"Failed to update standings graphics: {e}")

    # Update results graphics by calling the relevant synchronous function in another thread
    async def update_results_graphics(self, tiers, week):

        logger.info("Attempting to update results graphics")
        try:
            t1 = time.time()
            await asyncio.to_thread(update_r, tiers, week)
            logger.info(
                f"Successfully updated results graphics for {len(tiers)} tiers in {round(time.time() - t1, 3)}s"
            )
        except Exception as e:
            logger.error(f"Failed to update results graphics: {e}")

    # Ping reporting cog
    @app_commands.command(description="Ping the reporting cog")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def ping_reporting(self, interaction: discord.Interaction):
        logger.debug(f"/ping_reporting used by {interaction.user.id}")
        await interaction.response.send_message("Pong!", ephemeral=True)

    # Record a new sub entry in the database
    @app_commands.command(description="Register a new sub (Any playstation -> PS4)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def register_sub(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        name: str,
        platform: Literal["steam", "epic", "ps4", "xbox"],
        platform_id: str,
    ):
        logger.debug(f"/register_sub used by {interaction.user.id}")
        async with self.bot.pool.acquire() as con:
            await con.execute(
                "INSERT INTO players(id, status, name, platform, platform_id) VALUES(?, ?, ?, ?, ?)",
                (user.id, "sub", name, platform, platform_id),
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
        wp1: str = None,
        wp2: str = None,
        wp3: str = None,
        lp1: str = None,
        lp2: str = None,
        lp3: str = None,
        played_previously: int = 0,
    ):
        logger.debug(f"/report_3v3 used by {interaction.user.id}")

        # Store non None user objects of players
        winning_players = [p for p in [wp1, wp2, wp3] if p is not None]
        losing_players = [p for p in [lp1, lp2, lp3] if p is not None]

        # Validate the arguments
        arg_validation = await self.validate_report_args(
            tier, winning_org, losing_org, played_previously, winning_players, losing_players, 3
        )

        # If argument validation failed, arg_validation will contain the error message
        if arg_validation is not None:
            await interaction.response.send_message(arg_validation)
            return

        logger.info("Report arguments validated successfully")

        # If no player arguments were entered, the winning and losing players were as expected
        if len(winning_players) + len(losing_players) == 0:
            async with self.bot.pool.acquire() as con:
                res = await con.execute(
                    "SELECT name, org FROM players WHERE tier = ? AND (org = ? OR org = ?) AND status = 'main'",
                    (tier, winning_org, losing_org),
                )
                for row in await res.fetchall():
                    if row[1] == winning_org:
                        winning_players.append(row[0])
                    else:
                        losing_players.append(row[0])

        game_id = await self.generate_game_id(winning_org, losing_org, tier, 3)

        # Make sure that both orgs field a roster in this tier
        if winning_players == [] or losing_players == []:
            logger.warning("Report failing as a team does not field a roster in this tier")
            await interaction.response.send_message(
                "One or more teams do not field a roster in this tier"
            )
            return

        # Construct Series_Result for this report
        result_obj = Series_Result(
            game_id,
            tier,
            3,
            winning_org,
            losing_org,
            score,
            played_previously,
            winning_players,
            losing_players,
        )

        # Store the result in the database
        await self.store_series_result(result_obj)

        logger.info(f"Successfully stored series with game id {game_id}")

        # Generate the report embed and send it
        embed = await self.generate_report_embed(result_obj)

        await interaction.response.send_message(embed=embed)

        # Find what week the fixture is in
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                """SELECT week FROM fixtures WHERE 
                tier = ? AND ? IN(org_1, org_2) AND ? IN(org_1, org_2)""",
                (tier, ORGS[winning_org]["id"], ORGS[losing_org]["id"]),
            )
            # This will never fail as the format is round robin, meaning all possible matches
            # (that get to this point) must be scheduled at some point
            week = (await res.fetchone())["week"]

        await self.update_standings_graphics(["Overall", tier])
        await self.update_results_graphics([tier], week)

    @app_commands.command(description="Report a 2v2 result")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def report_2v2(
        self,
        interaction: discord.Interaction,
        tier: str,
        winning_org: str,
        losing_org: str,
        score: Literal["2-0", "2-1"],
        wp1: str,
        wp2: str,
        lp1: str,
        lp2: str,
        played_previously: int = 0,
    ):

        logger.debug(f"/report_2v2 used by {interaction.user.id}")

        # Store non None user objects of players
        winning_players = [wp1, wp2]
        losing_players = [lp1, lp2]

        # Validate the arguments
        arg_validation = await self.validate_report_args(
            tier, winning_org, losing_org, played_previously, winning_players, losing_players, 2
        )

        # If argument validation failed, arg_validation will contain the error message
        if arg_validation is not None:
            await interaction.response.send_message(arg_validation)
            return

        logger.info("Report arguments validated successfully")

        game_id = await self.generate_game_id(winning_org, losing_org, tier, 2)

        # Make sure that both orgs field a roster in this tier
        if winning_players == [] or losing_players == []:
            logger.warning("Report failing as a team does not field a roster in this tier")
            await interaction.response.send_message(
                "One or more teams do not field a roster in this tier"
            )
            return

        # Construct Series_Result for this report
        result_obj = Series_Result(
            game_id,
            tier,
            2,
            winning_org,
            losing_org,
            score,
            played_previously,
            winning_players,
            losing_players,
        )

        # Store the result in the database
        await self.store_series_result(result_obj)

        logger.info(f"Successfully stored series with game id {game_id}")

        # Generate the report embed and send it
        embed = await self.generate_report_embed(result_obj)

        await interaction.response.send_message(embed=embed)

        # Find what week the fixture is in
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                """SELECT week FROM fixtures WHERE 
                tier = ? AND ? IN(org_1, org_2) AND ? IN(org_1, org_2)""",
                (tier, ORGS[winning_org]["id"], ORGS[losing_org]["id"]),
            )
            # This will never fail as the format is round robin, meaning all possible matches
            # (that get to this point) must be scheduled at some point
            week = (await res.fetchone())["week"]

        await self.update_standings_graphics(["Overall", tier])
        await self.update_results_graphics([tier], week)

    @app_commands.command(description="Report a 1v1 result")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def report_1v1(
        self,
        interaction: discord.Interaction,
        tier: str,
        winning_org: str,
        losing_org: str,
        score: Literal["2-0", "2-1"],
        wp1: str,
        lp1: str,
        played_previously: int = 0,
    ):

        logger.debug(f"/report_1v1 used by {interaction.user.id}")

        # Store non None user objects of players
        winning_players = [wp1]
        losing_players = [lp1]

        # Validate the arguments
        arg_validation = await self.validate_report_args(
            tier, winning_org, losing_org, played_previously, winning_players, losing_players, 1
        )

        # If argument validation failed, arg_validation will contain the error message
        if arg_validation is not None:
            await interaction.response.send_message(arg_validation)
            return

        logger.info("Report arguments validated successfully")

        game_id = await self.generate_game_id(winning_org, losing_org, tier, 1)

        # Make sure that both orgs field a roster in this tier
        if winning_players == [] or losing_players == []:
            logger.warning("Report failing as a team does not field a roster in this tier")
            await interaction.response.send_message(
                "One or more teams do not field a roster in this tier"
            )
            return

        # Construct Series_Result for this report
        result_obj = Series_Result(
            game_id,
            tier,
            1,
            winning_org,
            losing_org,
            score,
            played_previously,
            winning_players,
            losing_players,
        )

        # Store the result in the database
        await self.store_series_result(result_obj)

        logger.info(f"Successfully stored series with game id {game_id}")

        # Generate the report embed and send it
        embed = await self.generate_report_embed(result_obj)

        await interaction.response.send_message(embed=embed)

        # Find what week the fixture is in
        async with self.bot.pool.acquire() as con:
            res = await con.execute(
                """SELECT week FROM fixtures WHERE 
                tier = ? AND ? IN(org_1, org_2) AND ? IN(org_1, org_2)""",
                (tier, ORGS[winning_org]["id"], ORGS[losing_org]["id"]),
            )
            # This will never fail as the format is round robin, meaning all possible matches
            # (that get to this point) must be scheduled at some point
            week = (await res.fetchone())["week"]

        await self.update_standings_graphics(["Overall", tier])
        await self.update_results_graphics([tier], week)

    @report_3v3.autocomplete("winning_org")
    @report_3v3.autocomplete("losing_org")
    @report_2v2.autocomplete("winning_org")
    @report_2v2.autocomplete("losing_org")
    @report_1v1.autocomplete("winning_org")
    @report_1v1.autocomplete("losing_org")
    async def org_autocomplete(self, interaction: discord.Interaction, current: str):

        choices = []
        matched_orgs = [o for o in ORGS.keys() if o.lower().startswith(current.lower())]
        for org in matched_orgs:
            choices.append(app_commands.Choice(name=org, value=org))

        logger.debug(f"Generated {len(choices)} org choices")
        return choices

    @report_3v3.autocomplete("tier")
    @report_2v2.autocomplete("tier")
    @report_1v1.autocomplete("tier")
    async def tier_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        matched_tiers = [t for t in TIERS.keys() if t.lower().startswith(current.lower())]
        for tier in matched_tiers:
            choices.append(app_commands.Choice(name=tier, value=tier))

        logger.debug(f"Generated {len(choices)} tier choices")
        return choices

    @report_3v3.autocomplete("wp1")
    @report_3v3.autocomplete("wp2")
    @report_3v3.autocomplete("wp3")
    @report_3v3.autocomplete("lp1")
    @report_3v3.autocomplete("lp2")
    @report_3v3.autocomplete("lp3")
    @report_2v2.autocomplete("wp1")
    @report_2v2.autocomplete("wp2")
    @report_2v2.autocomplete("lp1")
    @report_2v2.autocomplete("lp2")
    @report_1v1.autocomplete("wp1")
    @report_1v1.autocomplete("lp1")
    async def players_autocomplete(self, interaction: discord.Interaction, current: str):

        if self.PLAYERS == [] and self.SUBS == []:
            await self.get_players()
            await self.get_subs()

        choices = []
        matched_subs = [p for p in self.SUBS if p.lower().startswith(current.lower())]
        for player in matched_subs:
            if len(choices) > 23:
                logger.debug("Truncating autocomplete choices (subs)")
                break
            else:
                choices.append(app_commands.Choice(name=f"{player} (SUB)", value=player))

        matched_players = [p for p in self.PLAYERS if p.lower().startswith(current.lower())]
        for player in matched_players:
            if len(choices) > 23:
                logger.debug("Truncating autocomplete choices (players)")
                break
            else:
                choices.append(app_commands.Choice(name=player, value=player))

        logger.debug(f"Generated {len(choices)} player choices")
        return choices


# Object to store all the fields generated by a series report
class Series_Result:
    def __init__(
        self,
        game_id,
        tier,
        mode,
        winning_org,
        losing_org,
        score,
        played_previously,
        winning_players,
        losing_players,
    ):
        self.game_id = game_id
        self.tier = tier
        self.mode = mode
        self.winning_org = winning_org
        self.losing_org = losing_org
        self.score = score
        self.played_previously = played_previously
        self.winning_players = winning_players
        self.losing_players = losing_players


async def setup(bot):
    await bot.add_cog(Reporting(bot))
