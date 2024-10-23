# f1: get stats for a specific game id
# take in a game id
# use game id to find players, report time, and played_previously
# if played previously is 0, derive start time (start of day)
# if played previously is >0, derive start time (start of day) and end time (end of day)
# filter replays with players, start time, and end time
# get the individual replays
# if the guid is new, store the guid in the relevant series log, the game stats in game_stats, and the stats for each player in player_stats

# f2: wider search for a specific game id
# take a set of players, a start time, and an end time
# follow same steps as f1
# except, require confirmation before saving any stats
import sqlite3
import datetime as dt
import utils.ballchasing_api as ballchasing_api
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
def get_max_games(mode):
    if mode == 3:
        return MAX_GAMES_3v3 * 2 - 1
    if mode == 2:
        return MAX_GAMES_2v2 * 2 - 1
    if mode == 1:
        return MAX_GAMES_1v1 * 2 - 1


# Store game and player stats from a specific match
def store_stats(cur, match_guid, game_id, date, replay_data):

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
    except KeyError:
        blue_goals = None

    try:
        orange_goals = replay_data["orange"]["stats"]["core"]["goals"]
    except KeyError:
        orange_goals = None

    if blue_goals is not None and orange_goals is not None and blue_goals != orange_goals:
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
    else:
        winner_goals = None
        loser_goals = None
        time_in_side_winner = None
        time_in_side_loser = None

    # Store game stats. Some values may be NULL if they were not included in the response
    cur.execute(
        "INSERT INTO game_stats VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            match_guid,
            url,
            timestamp,
            game_id,
            duration,
            overtime_duration,
            winner_goals,
            loser_goals,
            time_in_side_winner,
            time_in_side_loser,
        ),
    )

    all_players = replay_data["blue"]["players"] + replay_data["orange"]["players"]
    for player in all_players:
        platform = player["id"]["platform"]
        platform_id = player["id"]["id"]

        res = cur.execute(
            "SELECT name FROM players WHERE platform = ? AND platform_id = ?",
            (platform, platform_id),
        )
        name = res.fetchone()[0]

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


def get(cur, game_id, max_games, existing_guids, start, end, players):

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
                f"match_guild or date field not present - unable to save replay with id {replay["id"]}"
            )
            continue

        existing_guids.append(match_guid)

        # If the new replay will exceed the max number of replays for the mode, don't store it
        if len(existing_guids) > max_games:
            logger.error("Unable to store replay - too many replays in filter")
            break

        logger.info(f"Storing stats for {match_guid}")
        store_stats(cur, match_guid, game_id, date, replay_data)


def from_game_id(cur, game_id):
    # Get the mode, timestamp, played_previously, and players of the game id, and all of the
    # associated replay guids
    res = cur.execute(
        """SELECT 
            L.mode,
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

    max_games = get_max_games(data[0][0])

    report_timestamp = data[0][1]
    played_previously = data[0][2]

    # Get the replay guids already stored for this series
    existing_guids = [game[3] for game in data if game[3] is not None]
    logger.debug(f"Found {len(existing_guids)} existing replay guids for {game_id}")

    player_names = list(data[0][4:10])

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

    # Get the platform and platform id of the involved players
    res = cur.execute(
        "SELECT platform, platform_id FROM players WHERE name IN(?, ?, ?, ?, ?, ?)", player_names
    )
    players = res.fetchall()

    get(cur, game_id, max_games, existing_guids, start, end, players)


def from_game_id_with_time(cur, game_id, start_timestamp, end_timestamp):
    # Get the mode, timestamp, played_previously, and players of the game id, and all of the
    # associated replay guids
    res = cur.execute(
        """SELECT 
            L.mode,
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

    max_games = get_max_games(data[0][0])

    # Get the replay guids already stored for this series
    existing_guids = [game[1] for game in data if game[1] is not None]
    logger.debug(f"Found {len(existing_guids)} existing replay guids for {game_id}")

    player_names = list(data[0][2:8])

    # Get a datetime object of the start and end timestamps
    start = dt.datetime.fromtimestamp(start_timestamp, dt.timezone.utc)
    end = dt.datetime.fromtimestamp(end_timestamp, dt.timezone.utc)

    # Get the platform and platform id of the involved players
    res = cur.execute(
        "SELECT platform, platform_id FROM players WHERE name IN(?, ?, ?, ?, ?, ?)", player_names
    )
    players = res.fetchall()

    get(cur, game_id, max_games, existing_guids, start, end, players)


def from_replay_id(cur, game_id, replay_id):
    res = cur.execute(
        """SELECT L.mode, S.guid 
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

    max_games = get_max_games(data[0][0])

    # Get the replay guids already stored for this series
    existing_guids = [guid[1] for guid in data]
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
    store_stats(cur, match_guid, game_id, date, replay_data)


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

    # If a replay id is included, request that
    if data[2] is not None:
        logger.info("Getting replay from replay id")
        from_replay_id(cur, data[1], data[2])
    # If there is no replay id but timestamps are included, search using them
    elif data[3] is not None and data[4] is not None:
        logger.info("Getting replay from game id with specified times")
        from_game_id_with_time(cur, data[1], data[3], data[4])
    # If only a game id is included, request that
    else:
        logger.info("Getting replay from game id")
        from_game_id(cur, data[1])

    # Delete the item that's been popped off the stack
    cur.execute(
        """DELETE FROM stats_stack 
        WHERE priority = (SELECT MAX(priority) FROM stats_stack)"""
    )

    con.commit()


if __name__ == "__main__":
    main()
