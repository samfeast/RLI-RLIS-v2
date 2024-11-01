import os
import sqlite3
import json

import logging

from PIL import Image, ImageFont, ImageDraw

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

ORGS = config["ORGS"]

MAX_GAMES_3v3 = config["MAX_GAMES_3v3"]
MAX_GAMES_2v2 = config["MAX_GAMES_2v2"]
MAX_GAMES_1v1 = config["MAX_GAMES_1v1"]

logger = logging.getLogger("script.draw_stats")

# Suppress spammy PIL image editing logs
logging.getLogger("PIL.PngImagePlugin").setLevel(30)

logging.basicConfig(
    filename="../logs/rlis.log",
    encoding="utf-8",
    datefmt="%Y-%m-%d %H:%M:%S",
    format="[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    level=logging.DEBUG,
)


def max_games(mode):
    if mode == 3:
        return 2 * MAX_GAMES_3v3 - 1
    elif mode == 2:
        return 2 * MAX_GAMES_2v2 - 1
    elif mode == 1:
        return 2 * MAX_GAMES_1v1 - 1


def draw_data(game_id, data):

    # Stats which need to be drawn and the required decimal precision
    stats_to_draw = {
        "score": 0,
        "goals": 1,
        "assists": 1,
        "shots": 1,
        "saves": 1,
        "demos_inflicted": 1,
        "avg_speed": 0,
    }
    # If the mode is 1v1, don't draw assists
    if data["mode"] == 1:
        stats_to_draw.pop("assists")

    # Delete the stat graphic if it exists
    try:
        os.remove(f"../data/graphics/{game_id}.png")
        logger.debug("Outdated stats graphic removed")
    except OSError:
        pass

    # Attempt to load the template file for the relevant mode
    try:
        image = Image.open(f"assets/templates/stat_template_{data['mode']}.png")
        logger.info("Successfully opened template file")
    except FileNotFoundError:
        logger.error("Failed to draw stats as template file does not exist")
        return

    image_editable = ImageDraw.Draw(image)

    # Draw '<team 1> vs <team 2>'
    font = ImageFont.truetype("assets/fonts/SourceSansPro-Black.ttf", 96)
    text = f"{data['winning_org']} vs {data['losing_org']}"
    w = font.getlength(text)
    image_editable.text(((1512 - w) / 2, 15), text, (255, 255, 255), font=font)

    # Draw '<tier> <mode> - Week <week>'
    font = ImageFont.truetype("assets/fonts/SourceSansPro-Black.ttf", 64)
    text = f"{data['tier']} {data['mode']}v{data['mode']} — Week {data['week']}"
    w = font.getlength(text)
    image_editable.text(((1512 - w) / 2, 128), text, (167, 167, 167), font=font)

    logger.info(f"Starting to draw player stats")

    # Draw player stats - maintain pointers of the index of player on each side of the graphic
    i_left = 0
    i_right = 0
    for player in data[data["winning_org"]] | data[data["losing_org"]]:
        if player in data[data["winning_org"]]:
            player_stats = data[data["winning_org"]][player]
            side = -1
            i = i_left
            i_left += 1
        else:
            player_stats = data[data["losing_org"]][player]
            side = 1
            i = i_right
            i_right += 1

        # Draw player name, if the player name is longer than 140px (the size of the bounding box),
        # scale it down incrementally until it fits. For every pt the font size decreases by, draw
        # the text that many pixels lower
        player_name_size = 36
        font = ImageFont.truetype("assets/fonts/SourceSansPro-Regular.ttf", player_name_size)
        w = font.getlength(player)
        while w > 140:
            font = ImageFont.truetype("assets/fonts/SourceSansPro-Regular.ttf", player_name_size)
            w = font.getlength(player)
            player_name_size -= 2
        image_editable.text(
            (
                ((1512 - w) / 2) + (150 * side) + (140 * i * side),
                283 + (36 - player_name_size),
            ),
            player,
            (255, 255, 255),
            font=font,
        )

        # Draw the stats for the player
        # j represents the location index of the stat being drawn
        j = 0
        for stat in stats_to_draw:
            font = ImageFont.truetype("assets/fonts/SourceSansPro-Regular.ttf", 24)
            # If no stat is stored, draw '?', otherwsie round it to the correct number
            # of decimal places
            if player_stats[stat] is None:
                text = "?"
            else:
                stat_value = round(player_stats[stat], stats_to_draw[stat])
                if stats_to_draw[stat] == 0:
                    stat_value = int(stat_value)

                text = str(stat_value)
            w = font.getlength(text)
            image_editable.text(
                (((1512 - w) / 2) + (150 * side) + (140 * i * side), 353 + 50 * j),
                text,
                (255, 255, 255),
                font=font,
            )

            j += 1

    # Draw the stat bars
    i = 0
    for stat in stats_to_draw:

        # Get the total value of the stat for each org
        winning_org_total = sum(
            p[stat] if p[stat] is not None else 0 for p in data[data["winning_org"]].values()
        )
        losing_org_total = sum(
            p[stat] if p[stat] is not None else 0 for p in data[data["losing_org"]].values()
        )

        # Calculate the length of the bar for the losing org
        losing_org_length = round(
            (losing_org_total / (winning_org_total + losing_org_total)) * 136
        )

        # Draw the winning orgs bar to be the full length, and the losing org to be the required length
        image_editable.rectangle(
            [(688, 383 + 50 * i), (823, 384 + 50 * i)], fill=ORGS[data["winning_org"]]["colour"]
        )

        image_editable.rectangle(
            [(823 - losing_org_length, 383 + 50 * i), (823, 384 + 50 * i)],
            fill=ORGS[data["losing_org"]]["colour"],
        )

        # Draw a 2x2 white square where they meet
        image_editable.rectangle(
            [(822 - losing_org_length, 383 + 50 * i), (823 - losing_org_length, 384 + 50 * i)],
            fill="#ffffff",
        )

        i += 1

    logger.info(f"Finished drawing player stats and stat bars, now drawing goals section")

    # Open and paste the org logos
    logo_left = Image.open(f"assets/logos/{ORGS[data['winning_org']]['logo_file']}")
    logo_right = Image.open(f"assets/logos/{ORGS[data['losing_org']]['logo_file']}")

    image.paste(logo_left, (140 * (3 - data["mode"]), 392), mask=logo_left)
    image.paste(logo_right, (1256 - 140 * (3 - data["mode"]), 392), mask=logo_right)

    # The 3v3 template uses a different layout as it's BO5 - adjust the lower section accordingly
    offset_org_names = 0
    start_x_adjust = 38
    if data["mode"] == 3:
        offset_org_names = -73
        start_x_adjust -= 73

    # Draw the winning org and losing org text (winning org for the series is always on top)
    font = ImageFont.truetype("assets/fonts/SourceSansPro-SemiBold.ttf", 32)
    text = data["winning_org"].upper()
    w = font.getlength(text)
    image_editable.text(
        (((1512 - w) / 2) - w / 2 - 6 + offset_org_names, 792),
        text,
        ORGS[data["winning_org"]]["colour"],
        font=font,
    )

    text = data["losing_org"].upper()
    w = font.getlength(text)
    image_editable.text(
        (((1512 - w) / 2) - w / 2 - 6 + offset_org_names, 842),
        text,
        ORGS[data["losing_org"]]["colour"],
        font=font,
    )

    # Get the list of goals in each game for the winning and losing orgs respectively
    winning_org_goals = data["games"][data["winning_org"]]
    losing_org_goals = data["games"][data["losing_org"]]

    # Make sure that these lists are the same length, since both teams have played the same number
    # of games
    if len(winning_org_goals) != len(losing_org_goals):
        logger.error("Winning org goals and losing org goals do not have the same length")
        return

    # Draw the goals for each org in each game. If the game was not played (e.g games 4 and 5 in a
    # 3-0), draw '-'
    font = ImageFont.truetype("assets/fonts/SourceSansPro-Regular.ttf", 32)
    for i in range(max_games(data["mode"])):
        if i < len(winning_org_goals):
            text_top = str(winning_org_goals[i])
        else:
            text_top = "-"

        if i < len(losing_org_goals):
            text_bottom = str(losing_org_goals[i])
        else:
            text_bottom = "-"

        colour_top = (255, 255, 255)
        colour_bottom = (255, 255, 255)

        # Change the colour of the goals of the winning org
        if text_top != "-" and text_bottom != "-":
            if winning_org_goals[i] > losing_org_goals[i]:
                colour_top = ORGS[data["winning_org"]]["colour"]
            else:
                colour_bottom = ORGS[data["losing_org"]]["colour"]

        w = font.getlength(str(text_top))
        image_editable.text(
            (((1512 - w) / 2) + start_x_adjust + 73 * i, 792),
            text_top,
            colour_top,
            font=font,
        )

        w = font.getlength(text_bottom)
        image_editable.text(
            (((1512 - w) / 2) + start_x_adjust + 73 * i, 842),
            text_bottom,
            colour_bottom,
            font=font,
        )

    logger.info(f"Finishing drawing graphic, saving {game_id}.png")

    image.save(f"../data/graphics/{game_id}.png", compress_level=5)


def get_data(game_id):

    data = {}

    con = sqlite3.connect("../data/rlis_data.db")
    cur = con.cursor()

    logger.info("Connected to database")

    # Get the series data
    res = cur.execute(
        """SELECT L.tier, L.mode, L.winning_org, L.losing_org, 
        P.wp1, P.wp2, P.wp3, P.lp1, P.lp2, P.lp3 
        FROM series_log AS L JOIN series_players AS P 
        ON L.game_id = P.game_id WHERE L.game_id = ?""",
        (game_id,),
    )

    series_data = res.fetchone()

    if series_data is None:
        logger.error("Game id not found")
        return

    # Store the tier, mode, winning org and losing org
    data["tier"] = series_data[0]
    data["mode"] = series_data[1]
    data["winning_org"] = series_data[2]
    data["losing_org"] = series_data[3]

    # Get the org ids to query the fixtures table
    winning_org_id = ORGS[series_data[2]]["id"]
    losing_org_id = ORGS[series_data[3]]["id"]

    # Find the week in which this match took place
    res = cur.execute(
        """SELECT week FROM fixtures 
        WHERE ? IN (org_1, org_2) AND ? IN (org_1, org_2) AND tier = ?""",
        (winning_org_id, losing_org_id, series_data[0]),
    )

    week = res.fetchone()

    # Make sure the series is fixtured - if it is, store the week
    if week is not None:
        data["week"] = week[0]
    else:
        logger.error("Fixture not found")
        return

    # Get the non-none player names
    winning_players = [p for p in [series_data[4], series_data[5], series_data[6]] if p != None]
    losing_players = [p for p in [series_data[7], series_data[8], series_data[9]] if p != None]

    player_stat_template = {
        "score": None,
        "goals": None,
        "assists": None,
        "shots": None,
        "saves": None,
        "demos_inflicted": None,
        "avg_speed": None,
    }

    # Store a blank stat template for each winning player as the child of the winning org
    data[series_data[2]] = {}
    # Store a blank stat template for each losing player as the child of the losing org
    data[series_data[3]] = {}

    # Get the average stats for all the replay guids associated with this game id
    res = cur.execute(
        """SELECT name, AVG(score), AVG(goals), AVG(assists), AVG(shots), AVG(saves), 
        AVG(demos_inflicted), AVG(avg_speed) 
        FROM player_stats WHERE guid IN (SELECT guid FROM game_stats WHERE game_id = ?) 
        GROUP BY name ORDER BY AVG(score) DESC""",
        (game_id,),
    )

    all_player_stats = res.fetchall()

    # Go through each player, and store their stats to the relevant dictionary
    for player in all_player_stats:
        if player[0] in winning_players:
            data[series_data[2]][player[0]] = player_stat_template.copy()
            player_stats = data[series_data[2]][player[0]]
            player_stats["score"] = player[1]
            player_stats["goals"] = player[2]
            player_stats["assists"] = player[3]
            player_stats["shots"] = player[4]
            player_stats["saves"] = player[5]
            player_stats["demos_inflicted"] = player[6]
            player_stats["avg_speed"] = player[7]
        elif player[0] in losing_players:
            data[series_data[3]][player[0]] = player_stat_template.copy()
            player_stats = data[series_data[3]][player[0]]
            player_stats["score"] = player[1]
            player_stats["goals"] = player[2]
            player_stats["assists"] = player[3]
            player_stats["shots"] = player[4]
            player_stats["saves"] = player[5]
            player_stats["demos_inflicted"] = player[6]
            player_stats["avg_speed"] = player[7]
        else:
            logger.warning(f"{player[0]} is not a known player for this series")

    # Get the number of goals scored in each game in order, game 1 first
    res = cur.execute(
        """SELECT winning_org, losing_org, winner_goals, loser_goals 
                      FROM game_stats WHERE game_id = ? ORDER BY timestamp ASC""",
        (game_id,),
    )

    game_stats = res.fetchall()

    # Create lists to store the goals stored in each game
    data["games"] = {series_data[2]: [], series_data[3]: []}

    # Store the number of goals scored by each org in each game
    for game in game_stats:
        data["games"][game[0]].append(game[2])
        data["games"][game[1]].append(game[3])

    logger.info(f"Successfully loaded data for {game_id}")

    return data


def draw(game_id):
    data = get_data(game_id)
    draw_data(game_id, data)
