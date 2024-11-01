import sqlite3
import datetime as dt
import utils.ballchasing_api as ballchasing_api
from draw_stats import draw
import json
import time
import logging

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

BALLCHASING_KEY = config["BALLCHASING_KEY"]

MAX_GAMES_3v3 = config["MAX_GAMES_3v3"]
MAX_GAMES_2v2 = config["MAX_GAMES_2v2"]
MAX_GAMES_1v1 = config["MAX_GAMES_1v1"]

logger = logging.getLogger("script.get_stats")

logging.basicConfig(
    filename="../logs/rlis.log",
    encoding="utf-8",
    datefmt="%Y-%m-%d %H:%M:%S",
    format="[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    level=logging.DEBUG,
)


# Get the maximum number of replays for a series of a specific mode
def max_games_for_mode(mode):
    if mode == 3:
        return MAX_GAMES_3v3
    if mode == 2:
        return MAX_GAMES_2v2
    if mode == 1:
        return MAX_GAMES_1v1


def determine_winner(cur, game_id, replay_data):
    # Try and get the total goals scored by the blue and orange teams
    try:
        blue_goals = replay_data["blue"]["stats"]["core"]["goals"]
    except KeyError:
        blue_goals = None

    try:
        orange_goals = replay_data["orange"]["stats"]["core"]["goals"]
    except KeyError:
        orange_goals = None

    # If this condition is met the winner cannot be resolved, so return None
    if blue_goals is None or orange_goals is None or blue_goals == orange_goals:
        return None, None

    # Get the winning and losing player ids from the replay
    if blue_goals > orange_goals:
        game_winners = {
            (player["id"]["platform"], player["id"]["id"])
            for player in replay_data["blue"]["players"]
        }
        game_losers = {
            (player["id"]["platform"], player["id"]["id"])
            for player in replay_data["orange"]["players"]
        }
    else:
        game_winners = {
            (player["id"]["platform"], player["id"]["id"])
            for player in replay_data["orange"]["players"]
        }
        game_losers = {
            (player["id"]["platform"], player["id"]["id"])
            for player in replay_data["blue"]["players"]
        }

    # Get the orgs, mode, and player names from the series log
    res = cur.execute(
        """SELECT L.winning_org, L.losing_org, L.mode,
        P.wp1, P.wp2, P.wp3, P.lp1, P.lp2, P.lp3
        FROM series_log AS L JOIN series_players AS P ON L.game_id = P.game_id
        WHERE L.game_id = ?""",
        (game_id,),
    )
    data = res.fetchone()

    # Get the platforms and platform ids of the players on the winning org (for the series)
    res = cur.execute(
        """SELECT platform, platform_id FROM players 
        WHERE name IN(?, ?, ?)""",
        (data[3], data[4], data[5]),
    )
    # This will never fail since the players in series_players must have an entry in players
    series_winners = set(res.fetchall())

    # Get the platforms and platform ids of the players on the losing org (for the series)
    res = cur.execute(
        """SELECT platform, platform_id FROM players 
        WHERE name IN(?, ?, ?)""",
        (data[6], data[7], data[8]),
    )
    # This will never fail since the players in series_players must have an entry in players
    series_losers = set(res.fetchall())

    # Compare the sets to check if whether the series winners won/lost the game
    # This will always be correct since this function is only called when all the players
    # in the replay are known
    if series_winners == game_winners and series_losers == game_losers:
        return data[0], data[1]
    else:
        return data[1], data[0]


# Store game and player stats from a specific match
def store_stats(cur, match_guid, game_id, winning_org, losing_org, date, replay_data, alt_player):

    # Parse the date string into a unix timestamp
    timestamp = int(dt.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S%z").timestamp())

    try:
        url = f"https://ballchasing.com/replay/{replay_data["id"]}"
    except KeyError:
        url = None

    try:
        duration = replay_data["duration"]
    except KeyError:
        duration = None

    try:
        overtime_duration = replay_data["overtime_seconds"]
    except KeyError:
        overtime_duration = None

    try:
        blue_goals = replay_data["blue"]["stats"]["core"]["goals"]
        orange_goals = replay_data["orange"]["stats"]["core"]["goals"]
    except KeyError:
        blue_goals = None
        orange_goals = None

    # Get win dependent stats if possible
    if blue_goals is not None and orange_goals is not None:
        if blue_goals > orange_goals:
            winner_goals = blue_goals
            loser_goals = orange_goals

            try:
                time_in_side_winner = replay_data["blue"]["stats"]["ball"]["time_in_side"]
                time_in_side_loser = replay_data["orange"]["stats"]["ball"]["time_in_side"]
            except KeyError:
                time_in_side_winner = None
                time_in_side_loser = None
        else:
            winner_goals = orange_goals
            loser_goals = blue_goals

            try:
                time_in_side_winner = replay_data["orange"]["stats"]["ball"]["time_in_side"]
                time_in_side_loser = replay_data["blue"]["stats"]["ball"]["time_in_side"]
            except KeyError:
                time_in_side_winner = None
                time_in_side_loser = None

    # Store game stats. Some values may be NULL if they were not included in the response
    cur.execute(
        "INSERT INTO game_stats VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            match_guid,
            url,
            timestamp,
            game_id,
            winning_org,
            losing_org,
            duration,
            overtime_duration,
            winner_goals,
            loser_goals,
            time_in_side_winner,
            time_in_side_loser,
        ),
    )

    # Combine the blue and orange lists of players
    all_players = replay_data["blue"]["players"] + replay_data["orange"]["players"]
    for player in all_players:
        # Get the platform and platform id of the player from the response
        platform = player["id"]["platform"]
        platform_id = player["id"]["id"]

        # Get the name of the player from the platform and platform id
        res = cur.execute(
            "SELECT name FROM players WHERE platform = ? AND platform_id = ?",
            (platform, platform_id),
        )
        name = res.fetchone()

        # If the platform and platform id isn't recognised
        if name is None:
            # Check if the 'unknown' platform and platform id match that of the alternate player
            if alt_player[1][0] == platform and alt_player[1][1] == platform_id:
                name = alt_player[0]
            else:
                # If the platform and platform id isn't recognised at all, skip them
                logger.warning(
                    f"Failed to find {platform}:{platform_id} in players table, skipping"
                )
                continue
        else:
            name = name[0]

        try:
            duration = player["end_time"] - player["start_time"]
        except KeyError:
            duration = None

        try:
            goals = player["stats"]["core"]["goals"]
        except KeyError:
            goals = None

        try:
            assists = player["stats"]["core"]["assists"]
        except KeyError:
            assists = None

        try:
            saves = player["stats"]["core"]["saves"]
        except KeyError:
            saves = None

        try:
            shots = player["stats"]["core"]["shots"]
        except KeyError:
            shots = None

        try:
            score = player["stats"]["core"]["score"]
        except KeyError:
            score = None

        try:
            demos_inflicted = player["stats"]["demo"]["inflicted"]
        except KeyError:
            demos_inflicted = None

        try:
            demos_taken = player["stats"]["demo"]["taken"]
        except KeyError:
            demos_taken = None

        try:
            car = player["car_name"]
        except KeyError:
            try:
                car = player["car_id"]
            except KeyError:
                car = None

        try:
            boost_while_ss = player["stats"]["boost"]["amount_used_while_supersonic"]
        except KeyError:
            boost_while_ss = None

        try:
            time_0_boost = player["stats"]["boost"]["time_zero_boost"]
        except KeyError:
            time_0_boost = None

        try:
            avg_speed = player["stats"]["movement"]["avg_speed"]
        except KeyError:
            avg_speed = None

        try:
            dist_travelled = player["stats"]["movement"]["total_distance"]
        except KeyError:
            dist_travelled = None

        # Store player stats. Some values may be NULL if they were not included in the response
        cur.execute(
            "INSERT INTO player_stats VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                match_guid,
                name,
                game_id,
                duration,
                goals,
                assists,
                saves,
                shots,
                score,
                demos_inflicted,
                demos_taken,
                car,
                boost_while_ss,
                time_0_boost,
                avg_speed,
                dist_travelled,
            ),
        )

    logger.info(f"Finished storing game and player stats for {match_guid}")


def get(cur, game_id, max_games, existing_guids, start, end, players, alt_player):

    logger.debug(f"Filtering ballchasing between {start} and {end} with {players}")

    ballchasing = ballchasing_api.API(BALLCHASING_KEY)

    # Filter the replays, then get each one in turn
    filtered_replays = ballchasing.filter(start, end, players)
    logger.info(f"Filter found {filtered_replays["count"]} replays")
    for replay in filtered_replays["list"]:
        time.sleep(1)
        logger.debug(f"Getting replay with id {replay['id']}")
        replay_data = ballchasing.get(replay["id"])

        match_guid = replay_data.get("match_guid", None)
        date = replay_data.get("date", None)
        # If the guid already exists, skip it
        if match_guid in existing_guids:
            logger.info(f"Replay guid already stored, skipping ({match_guid})")
            continue
        # If the guid or date are not present, don't store it (these are required attributes)
        elif match_guid is None or date is None:
            logger.error(
                f"match_guild or date field not present - unable to save replay with id {replay['id']}"
            )
            continue

        existing_guids.append(match_guid)

        # If the new replay will exceed the max number of replays for the mode, don't store it
        if len(existing_guids) > max_games:
            logger.error("Unable to store replay - too many replays in filter")
            break

        winning_org, losing_org = determine_winner(cur, game_id, replay_data)
        # If the winning and losing orgs can't be resolved, dont store it
        if winning_org is None or losing_org is None:
            logger.error(f"Unable to resolve winning team - not saving {replay['id']}")
            continue

        logger.info(f"Storing stats for {match_guid}")
        store_stats(
            cur, match_guid, game_id, winning_org, losing_org, date, replay_data, alt_player
        )


def from_game_id(cur, game_id, alt_player, start_timestamp=None, end_timestamp=None):
    # Get the mode, timestamp, played_previously, and players of the game id, and all of the
    # associated replay guids
    res = cur.execute(
        """SELECT 
            L.mode,
            L.games_won_by_loser,
            L.timestamp, 
            L.played_previously, 
            S.guid, 
            P.wp1, P.wp2, P.wp3, 
            P.lp1, P.lp2, P.lp3 
        FROM 
            series_log AS L
        LEFT OUTER JOIN 
            game_stats AS S 
            ON L.game_id = S.game_id
        LEFT OUTER JOIN 
            series_players AS P 
            ON L.game_id = P.game_id 
        WHERE 
            L.game_id = ?""",
        (game_id,),
    )
    data = res.fetchall()

    if data == []:
        logger.warning(f"Could not find any report of game id {game_id}")
        return

    max_games = max_games_for_mode(data[0][0]) + data[0][1]

    report_timestamp = data[0][2]
    played_previously = data[0][3]

    # Get the replay guids already stored for this series
    existing_guids = [game[4] for game in data if game[4] is not None]
    logger.debug(f"Found {len(existing_guids)} existing replay guids for {game_id}")

    player_names = list(data[0][5:11])

    if start_timestamp is None or end_timestamp is None:
        # Get a datetime object of the reported unix timestamp
        report_datetime = dt.datetime.fromtimestamp(report_timestamp, dt.timezone.utc)

        # Get the start and end datetimes for the search
        if played_previously == 0:
            # If played previously is 0 look between the report and the start of the day
            end = report_datetime
            start = end.replace(hour=0, minute=0, second=0)
        else:
            # If played previously is >0, look for the whole day of the series
            end = report_datetime - dt.timedelta(days=played_previously - 1)
            end = end.replace(hour=0, minute=0, second=0)
            start = end - dt.timedelta(days=1)
    else:
        # Get a datetime object of the start and end timestamps
        start = dt.datetime.fromtimestamp(start_timestamp, dt.timezone.utc)
        end = dt.datetime.fromtimestamp(end_timestamp, dt.timezone.utc)

    # Get the platform and platform id of the involved players
    res = cur.execute(
        "SELECT platform, platform_id FROM players WHERE name IN(?, ?, ?, ?, ?, ?)", player_names
    )
    players = res.fetchall()

    get(cur, game_id, max_games, existing_guids, start, end, players, alt_player)


def from_replay_id(cur, game_id, replay_id, winning_org, losing_org, alt_player):
    res = cur.execute(
        """SELECT L.mode, L.games_won_by_loser, S.guid 
        FROM 
            series_log AS L 
        LEFT OUTER JOIN 
            game_stats AS S ON L.game_id = S.game_id 
        WHERE L.game_id = ?""",
        (game_id,),
    )

    data = res.fetchall()

    if data == []:
        logger.warning(f"Could not find any report of game id {game_id}")
        return

    max_games = max_games_for_mode(data[0][0]) + data[0][1]

    # Get the replay guids already stored for this series
    existing_guids = [guid[2] for guid in data if guid[2] is not None]
    logger.debug(f"Found {len(existing_guids)} existing replay guids for {game_id}")

    ballchasing = ballchasing_api.API(BALLCHASING_KEY)

    # Get the specified replay id, if it doesn't exist this will return {}
    replay_data = ballchasing.get(replay_id)

    if replay_data == {}:
        logger.warning(f"Replay id {replay_id} not found")
        return

    match_guid = replay_data.get("match_guid", None)
    date = replay_data.get("date", None)
    # If the guid already exists, skip it
    if match_guid in existing_guids:
        logger.info(f"Replay guid already stored, skipping ({match_guid})")
        return
    # If the guid or date are not present, don't store it (these are required attributes)
    elif match_guid is None or date is None:
        logger.error(
            f"match_guild or date field not present - unable to save replay with id {replay_id}"
        )
        return

    existing_guids.append(match_guid)

    # If the new replay will exceed the max number of replays for the mode, don't store it
    if len(existing_guids) > max_games:
        logger.error("Unable to store replay - too many replays in filter")
        return

    logger.info(f"Storing stats for {match_guid}")
    store_stats(cur, match_guid, game_id, winning_org, losing_org, date, replay_data, alt_player)


def main():
    con = sqlite3.connect("../data/rlis_data.db")
    cur = con.cursor()

    # Enforce referential key constraints for this session (since there may be insertions)
    cur.execute("PRAGMA foreign_keys = ON")

    # Pop the highest priority itme off the stack
    res = cur.execute(
        """SELECT * 
        FROM stats_stack 
        ORDER BY priority DESC 
        LIMIT 1"""
    )

    data = res.fetchone()

    if data is None:
        logger.debug("No stats on the stack, ending")
        return

    logger.info(f"Popped entry from stats stack - {data}")

    alt_player = (data[7], (data[8], data[9]))

    # If a replay id and winning/losing orgs are included, search for that
    if data[2] is not None and data[5] is not None and data[6] is not None:
        logger.info("Getting replay from replay id")
        from_replay_id(cur, data[1], data[2], data[5], data[6], alt_player)
    # If there is no replay id but timestamps are included, search using them
    elif data[3] is not None and data[4] is not None:
        logger.info("Getting replay from game id with specified times")
        from_game_id(cur, data[1], alt_player, start_timestamp=data[3], end_timestamp=data[4])
    # If only a game id is included, infer times
    else:
        logger.info("Getting replay from game id")
        from_game_id(cur, data[1], alt_player)

    # Delete the item that's been popped off the stack
    cur.execute(
        """DELETE FROM stats_stack 
        WHERE priority = (SELECT MAX(priority) FROM stats_stack)"""
    )

    # Update the number of replays stored and unpublish series in series log
    cur.execute(
        """UPDATE series_log 
        SET replays_stored = (SELECT COUNT(guid) FROM game_stats WHERE game_id = ?),
        published = 0 WHERE game_id = ?""",
        (data[1], data[1]),
    )

    con.commit()

    draw(data[1])


if __name__ == "__main__":
    main()
