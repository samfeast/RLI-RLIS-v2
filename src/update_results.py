import os
import sqlite3
import json

import logging

from PIL import Image, ImageFont, ImageDraw

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

ORGS = config["ORGS"]
TIERS = config["TIERS"]

MAX_GAMES_3v3 = config["MAX_GAMES_3v3"]
MAX_GAMES_2v2 = config["MAX_GAMES_2v2"]
MAX_GAMES_1v1 = config["MAX_GAMES_1v1"]

POINTS_3v3 = config["POINTS_3v3"]
POINTS_2v2 = config["POINTS_2v2"]
POINTS_1v1 = config["POINTS_1v1"]

logger = logging.getLogger("script.update_results")

# Suppress spammy PIL image editing logs
logging.getLogger("PIL.PngImagePlugin").setLevel(30)

logging.basicConfig(
    filename="../logs/rlis.log",
    encoding="utf-8",
    datefmt="%Y-%m-%d %H:%M:%S",
    format="[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    level=logging.DEBUG,
)


def edit_graphic(tier, week, data):

    # Delete stored graphic if it exists
    try:
        os.remove(f"../data/graphics/{tier.replace(' ', '_').lower()}_week_{week}.png")
        logger.debug("Outdated results graphic removed")
    except OSError:
        pass

    # Attempt to load the template file
    try:
        image = Image.open(f"assets/templates/results_template.png")
        logger.info("Successfully opened template file")
    except FileNotFoundError:
        logger.error("Failed to update results as template file does not exist")
        return

    image_editable = ImageDraw.Draw(image)

    # Draw tier text
    font = ImageFont.truetype("assets/fonts/SourceSansPro-Black.ttf", 80)
    w = font.getlength(f"{tier} Results")
    image_editable.text(((1512 - w) / 2, 60), f"{tier} Results", (255, 255, 255), font=font)
    # Draw week text
    font = ImageFont.truetype("assets/fonts/SourceSansPro-SemiBold.ttf", 48)
    w = font.getlength(f"Week {week}")
    image_editable.text(((1512 - w) / 2, 150), f"Week {week}", (180, 180, 180), font=font)

    logger.debug("Starting to draw result data")

    # Track whether the first, second, or third box is being drawn to
    pos_index = 0

    for match in data:

        # If no series in a match have been played, skip to the next match
        if data[match] == {}:
            continue

        # Draw the backing gradient which is displayed for series with something to show
        backing_gradient = Image.open(f"assets/templates/results_backing_gradient.png")
        image.paste(backing_gradient, (0, 290 + 270 * pos_index), mask=backing_gradient)

        # These a guaranteed to be populated since making it this far guarantees that at least one
        # mode has been played
        org_1_logo = None
        org_2_logo = None

        # Draw data for each mode in turn
        for i in range(3):
            try:
                series_data = data[match][3 - i]
            except KeyError:
                # If a key error is raised, the series has not been played yet, so skip to the next
                continue

            # Store the logo file names of the involved orgs to draw later
            org_1_logo = ORGS[series_data["org_1_name"]]["logo_file"]
            org_2_logo = ORGS[series_data["org_2_name"]]["logo_file"]

            # Draw the left org name
            font = ImageFont.truetype("assets/fonts/SourceSansPro-SemiBold.ttf", 40)
            w = font.getlength(series_data["org_1_name"])
            image_editable.text(
                (
                    ((1512 - w) / 2) - (w / 2) - 100,
                    300 + 270 * pos_index + 67 * i,
                ),
                series_data["org_1_name"],
                (255, 255, 255),
                font=font,
            )
            # Draw the right org name
            w = font.getlength(series_data["org_2_name"])
            image_editable.text(
                (
                    ((1512 - w) / 2) + (w / 2) + 100,
                    300 + 270 * pos_index + 67 * i,
                ),
                series_data["org_2_name"],
                (255, 255, 255),
                font=font,
            )

            # Draw the score
            score_str = f"{series_data["org_1_games"]} - {series_data["org_2_games"]}"
            font = ImageFont.truetype("assets/fonts/SourceSansPro-Black.ttf", 54)
            w = font.getlength(score_str)
            image_editable.text(
                (
                    (1512 - w) / 2,
                    300 + 270 * pos_index + 67 * i,
                ),
                score_str,
                (255, 255, 255),
                font=font,
            )

            # Draw the left roster
            font = ImageFont.truetype("assets/fonts/SourceSansPro-Light.ttf", 18)
            w = font.getlength(", ".join(series_data["org_1_roster"]))
            image_editable.text(
                (
                    ((1512 - w) / 2) - (w / 2) - 100,
                    348 + 270 * pos_index + 67 * i,
                ),
                ", ".join(series_data["org_1_roster"]),
                (200, 200, 200),
                font=font,
            )

            # Draw the right roster
            w = font.getlength(", ".join(series_data["org_2_roster"]))
            image_editable.text(
                (
                    ((1512 - w) / 2) + (w / 2) + 100,
                    348 + 270 * pos_index + 67 * i,
                ),
                ", ".join(series_data["org_2_roster"]),
                (200, 200, 200),
                font=font,
            )

        # Load the logo files, resize them, and paste them
        logo_1 = Image.open(f"assets/logos/{org_1_logo}")
        logo_2 = Image.open(f"assets/logos/{org_2_logo}")

        logo_1 = logo_1.resize((200, 200))
        logo_2 = logo_2.resize((200, 200))

        image.paste(logo_1, (112, 305 + 270 * pos_index), mask=logo_1)
        image.paste(logo_2, (1200, 305 + 270 * pos_index), mask=logo_2)

        # Increment to move on to the next result box
        pos_index += 1

    logger.debug("Finished drawing result data")

    # Save file compression level 5 to balance time and space
    image.save(
        f"../data/graphics/{tier.replace(' ', '_').lower()}_week_{week}.png", compress_level=5
    )

    logger.info("Successfully saved results graphic")


def get_data(tier, week):

    tier_id = TIERS[tier]

    con = sqlite3.connect("../data/rlis_data.db")
    cur = con.cursor()

    logger.info("Connected to database")

    # Get fixtures for specified week and tier in a deterministic order
    cur.execute(
        "SELECT org_1, org_2 FROM fixtures WHERE week = ? AND tier = ? ORDER BY org_1 DESC, org_2 DESC",
        (week, tier),
    )

    fixtures = cur.fetchall()

    logger.info("Successfully fetched fixtures from database")

    # Generate the game ids excluding the mode value
    partial_game_ids = [f"{max(match)}{min(match)}{tier_id}" for match in fixtures]

    data = {partial_id: {} for partial_id in partial_game_ids}

    logger.debug("Starting to query database for results")

    for partial_id in partial_game_ids:
        # Get the series info and players of all modes under the partial id
        cur.execute(
            """SELECT mode, winning_org, losing_org, games_won_by_loser,
            wp1, wp2, wp3, lp1, lp2, lp3 
            FROM series_log AS L JOIN series_players AS P ON L.game_id = P.game_id
            WHERE L.game_id IN (?, ?, ?)""",
            (f"{partial_id}3", f"{partial_id}2", f"{partial_id}1"),
        )
        match_data = cur.fetchall()
        for match in match_data:
            # Find the number of games won by the winning team / lost by the losing team
            if match[0] == 3:
                max_games = MAX_GAMES_3v3
            if match[0] == 2:
                max_games = MAX_GAMES_2v2
            if match[0] == 1:
                max_games = MAX_GAMES_1v1

            # Get the winning and losing players without None values
            winning_players = [p for p in [match[4], match[5], match[6]] if p is not None]
            losing_players = [p for p in [match[7], match[8], match[9]] if p is not None]

            if ORGS[match[1]]["id"] > ORGS[match[2]]["id"]:
                # In this case the winning org is org 1
                data[partial_id][match[0]] = {
                    "org_1_name": match[1],
                    "org_1_games": max_games,
                    "org_1_roster": winning_players,
                    "org_2_name": match[2],
                    "org_2_games": match[3],
                    "org_2_roster": losing_players,
                }
            else:
                # In this case the winning org is org 2
                data[partial_id][match[0]] = {
                    "org_1_name": match[2],
                    "org_1_games": match[3],
                    "org_1_roster": losing_players,
                    "org_2_name": match[1],
                    "org_2_games": max_games,
                    "org_2_roster": winning_players,
                }

    logger.debug("Finished querying database for results")

    return data


def update(tiers, week):
    # For each tier that needs a graphic generating, get the data, then edit the graphic
    for tier in tiers:
        logger.info(f"Generating results graphic for {tier}")
        data = get_data(tier, week)
        if data != {}:
            edit_graphic(tier, week, data)
