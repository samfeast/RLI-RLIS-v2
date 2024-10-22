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


def get(game_id):
    con = sqlite3.connect("../data/rlis_data.db")
    cur = con.cursor()

    # Enforce referential key constraints for this session (since there will be insertions)
    cur.execute("PRAGMA foreign_keys = ON")

    res = cur.execute("SELECT guid FROM game_stats WHERE game_id = ?", (game_id,))

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
        return None

    if data[0][0] == 3:
        max_games = MAX_GAMES_3v3 * 2 - 1
    if data[0][0] == 2:
        max_games = MAX_GAMES_2v2 * 2 - 1
    if data[0][0] == 1:
        max_games = MAX_GAMES_1v1 * 2 - 1

    report_timestamp = data[0][1]
    played_previously = data[0][2]

    # Get the replay guids already stored for this series
    existing_guids = [game[3] for game in data if game[3] is not None]
    logger.debug(f"Found {len(existing_guids)} existing replay guids for {game_id}")
    # Get the players, omitting NULL values
    player_names = list(data[0][4:10])

    # Get a datetime object of the reported unix timestamp
    report_datetime = dt.datetime.fromtimestamp(report_timestamp)

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

    ballchasing = ballchasing_api.API(BALLCHASING_KEY)

    logger.debug(f"Filtering ballchasing with start: {start}, end: {end}, and players: {players}")

    # Filter the replays, then get each one in turn
    filtered_replays = ballchasing.filter(start, end, players)
    logger.info(f"Filter found {filtered_replays["count"]} replays")
    for replay in filtered_replays["list"]:
        time.sleep(1)
        replay_data = ballchasing.get(replay["id"])

        # If the guid isn't present in the response, the replay can't be stored (as guid is PKey)
        try:
            # If the guid is already stored (e.g two players upload the same replay, skip it)
            if replay_data["match_guid"] in existing_guids:
                logger.info(f"Replay guid already stored, skipping ({replay_data["match_guid"]})")
                continue
        except KeyError:
            logger.error(
                f"match_guid field not present - unable to save replay with id {replay["id"]}"
            )
            continue

        existing_guids.append(replay_data["match_guid"])

        # If the new replay will exceed the max number of replays for the mode, don't store it
        if len(existing_guids) > max_games:
            logger.error("Unable to store replay - too many replays in filter")
            break

        # Store in game_stats
        # Store in player_stats
