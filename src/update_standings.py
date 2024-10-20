import os
import sqlite3
import json

import logging

from PIL import Image, ImageFont, ImageDraw

with open("../config.json", "r") as read_file:
    config = json.load(read_file)

ORGS = config["ORGS"]

POINTS_3v3 = config["POINTS_3v3"]
POINTS_2v2 = config["POINTS_2v2"]
POINTS_1v1 = config["POINTS_1v1"]

logger = logging.getLogger("script.update_standings")

# Suppress spammy PIL image editing logs
logging.getLogger("PIL.PngImagePlugin").setLevel(30)

logging.basicConfig(
    filename="../logs/rlis.log",
    encoding="utf-8",
    datefmt="%Y-%m-%d %H:%M:%S",
    format="[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    level=logging.DEBUG,
)


def edit_graphic(tier, data):
    # Filter out orgs which do not have a roster
    for org in list(data.keys()):
        if data[org]["roster"] == []:
            del data[org]

    # sort() sorts nested lists first by the first element, then second, etc
    # Therefore create a nested list where each inner list has elements ordered by tiebreak order
    to_sort = [
        [
            data[org]["points"],
            data[org]["series_won"] - data[org]["series_lost"],
            data[org]["games_won"] - data[org]["games_lost"],
            org,
        ]
        for org in data
    ]

    # Sort the list in descending order
    to_sort.sort(reverse=True)

    # Get the names of the orgs in order
    ordered_orgs = [record[3] for record in to_sort]

    logger.info("Sorted org standings")

    # Delete stored graphic if it exists
    try:
        os.remove(f"../data/graphics/{tier.replace(' ', '_').lower()}.png")
        logger.debug("Outdated standings graphic removed")
    except OSError:
        pass

    if tier == "Overall":
        template_file = f"standings_template_{len(ordered_orgs)}o.png"
    else:
        template_file = f"standings_template_{len(ordered_orgs)}.png"

    # Attempt to load the template file
    try:
        image = Image.open(f"assets/templates/{template_file}")
        logger.info("Successfully opened template file")
    except FileNotFoundError:
        logger.error("Failed to update standings as template file does not exist")
        return

    image_editable = ImageDraw.Draw(image)

    # Draw title text
    font = ImageFont.truetype("assets/fonts/SourceSansPro-Black.ttf", 80)
    text = f"{tier} Standings"

    w = font.getlength(text)
    image_editable.text(((1920 - w) / 2, 50), text, (255, 255, 251), font=font)

    logger.info("Starting to draw org data")

    for i in range(len(ordered_orgs)):

        org_data = data[ordered_orgs[i]]

        # Draw org names
        font = ImageFont.truetype("assets/fonts/SourceSansPro-Black.ttf", 56)
        image_editable.text(
            (481, 379 + (i - 1) * 130),
            ordered_orgs[i],
            (255, 255, 251),
            font=font,
        )

        # Draw points
        w = font.getlength(str(org_data["points"]))
        image_editable.text(
            (((1920 - w) / 2) + 653, 391 + (i - 1) * 130),
            str(org_data["points"]),
            (255, 255, 251),
            font=font,
        )

        # Draw rosters
        font = ImageFont.truetype("assets/fonts/SourceSansPro-Light.ttf", 24)
        image_editable.text(
            (481, 451 + (i - 1) * 130),
            ", ".join(org_data["roster"]),
            (185, 185, 181),
            font=font,
        )

        # Draw game record
        font = ImageFont.truetype("assets/fonts/SourceSansPro-SemiBold.ttf", 48)
        w = font.getlength(f"{org_data["games_won"]} - {org_data["games_lost"]}")
        image_editable.text(
            (((1920 - w) / 2) + 411, 398 + (i - 1) * 130),
            f"{org_data["games_won"]} - {org_data["games_lost"]}",
            (255, 255, 251),
            font=font,
        )

        # Draw series record
        w = font.getlength(f"{org_data["series_won"]} - {org_data["series_lost"]}")
        image_editable.text(
            (((1920 - w) / 2) + 111, 398 + (i - 1) * 130),
            f"{org_data["series_won"]} - {org_data["series_lost"]}",
            (255, 255, 251),
            font=font,
        )

        org_logo_file = ORGS[ordered_orgs[i]]["logo_file"]

        # Paste resized logos
        logo = Image.open(f"assets/logos/{org_logo_file}")
        logo = logo.resize((100, 100))
        image.paste(logo, (339, 385 + (i - 1) * 130), mask=logo)

    logger.info("Finished drawing org data")

    # Save file compression level 5 to balance time and space
    image.save(f"../data/graphics/{tier.replace(' ', '_').lower()}.png", compress_level=5)

    logger.info("Successfully saved standings graphic")


def get_data(tier):
    con = sqlite3.connect("../data/rlis_data.db")
    cur = con.cursor()
    logger.info("Connected to database")

    data = {
        org: {
            "points": 0,
            "series_won": 0,
            "series_lost": 0,
            "games_won": 0,
            "games_lost": 0,
            "roster": [],
        }
        for org in ORGS.keys()
    }

    logger.info("Beginning to query database for org data")

    # Get rosters (or manager in case of Overall)
    if tier == "Overall":
        for org in data:
            data[org]["roster"] = [ORGS[org]["manager"]]
        tier_str = tier
        # If the tier is Overall, query the wildcard character to get all tiers
        tier = "%"
    else:
        res = cur.execute("SELECT name, org FROM players WHERE tier = ?", (tier,))
        for row in res.fetchall():
            data[row[1]]["roster"].append(row[0])

    # Points
    res = cur.execute(
        """
        SELECT winning_org, SUM(points) AS total_points 
        FROM
        (SELECT winning_org, ? AS points FROM series_log_3v3 WHERE tier LIKE ? 
        UNION ALL 
        SELECT winning_org, ? AS points FROM series_log_2v2 WHERE tier LIKE ? 
        UNION ALL 
        SELECT winning_org, ? AS points FROM series_log_1v1 WHERE tier LIKE ?) 
        GROUP BY winning_org""",
        (POINTS_3v3, tier, POINTS_2v2, tier, POINTS_1v1, tier),
    )
    for row in res.fetchall():
        data[row[0]]["points"] = row[1]

    # Series won
    res = cur.execute(
        """
        SELECT winning_org, COUNT(winning_org) AS series_won
        FROM
        (SELECT winning_org FROM series_log_3v3 WHERE tier LIKE ? 
        UNION ALL 
        SELECT winning_org FROM series_log_2v2 WHERE tier LIKE ? 
        UNION ALL 
        SELECT winning_org FROM series_log_1v1 WHERE tier LIKE ?) 
        GROUP BY winning_org;""",
        (tier, tier, tier),
    )

    for row in res.fetchall():
        data[row[0]]["series_won"] = row[1]

    # Series lost
    res = cur.execute(
        """
        SELECT losing_org, COUNT(losing_org) AS series_lost
        FROM
        (SELECT losing_org FROM series_log_3v3 WHERE tier LIKE ? 
        UNION ALL 
        SELECT losing_org FROM series_log_2v2 WHERE tier LIKE ? 
        UNION ALL 
        SELECT losing_org FROM series_log_1v1 WHERE tier LIKE ?) 
        GROUP BY losing_org;""",
        (tier, tier, tier),
    )

    for row in res.fetchall():
        data[row[0]]["series_lost"] = row[1]

    # Games won as winner
    res = cur.execute(
        """
        SELECT winning_org, SUM(games) AS games_won_as_winner
        FROM
        (SELECT winning_org, 3 AS games FROM series_log_3v3 WHERE tier LIKE ? 
        UNION ALL 
        SELECT winning_org, 2 AS games FROM series_log_2v2 WHERE tier LIKE ? 
        UNION ALL 
        SELECT winning_org, 2 AS games FROM series_log_1v1 WHERE tier LIKE ?) 
        GROUP BY winning_org""",
        (tier, tier, tier),
    )
    for row in res.fetchall():
        data[row[0]]["games_won"] = row[1]

    # Games lost as loser
    res = cur.execute(
        """
        SELECT losing_org, SUM(games) AS games_lost_as_loser
        FROM
        (SELECT losing_org, 3 AS games FROM series_log_3v3 WHERE tier LIKE ? 
        UNION ALL 
        SELECT losing_org, 2 AS games FROM series_log_2v2 WHERE tier LIKE ? 
        UNION ALL 
        SELECT losing_org, 2 AS games FROM series_log_1v1 WHERE tier LIKE ?) 
        GROUP BY losing_org""",
        (tier, tier, tier),
    )
    for row in res.fetchall():
        data[row[0]]["games_lost"] = row[1]

    # Games won as loser
    res = cur.execute(
        """
        SELECT losing_org, SUM(games_won_by_loser) AS games_won_as_loser
        FROM
        (SELECT losing_org, games_won_by_loser FROM series_log_3v3 WHERE tier LIKE ? 
        UNION ALL 
        SELECT losing_org, games_won_by_loser FROM series_log_2v2 WHERE tier LIKE ? 
        UNION ALL 
        SELECT losing_org, games_won_by_loser FROM series_log_1v1 WHERE tier LIKE ?) 
        GROUP BY losing_org""",
        (tier, tier, tier),
    )
    for row in res.fetchall():
        data[row[0]]["games_won"] += row[1]

    # Games lost as winner
    res = cur.execute(
        """
        SELECT winning_org, SUM(games_won_by_loser) AS games_lost_as_winner
        FROM
        (SELECT winning_org, games_won_by_loser FROM series_log_3v3 WHERE tier LIKE ? 
        UNION ALL 
        SELECT winning_org, games_won_by_loser FROM series_log_2v2 WHERE tier LIKE ? 
        UNION ALL 
        SELECT winning_org, games_won_by_loser FROM series_log_1v1 WHERE tier LIKE ?) 
        GROUP BY winning_org""",
        (tier, tier, tier),
    )
    for row in res.fetchall():
        data[row[0]]["games_lost"] += row[1]

    # Round the points to ensure there isn't floating point inaccuracy
    # If the tier is overall, find how many teams the org has, and divide to get an average
    for org in data:
        # If tier is '%' then the Overall standings are being generated
        if tier == "%":
            # Get the number of distinct tiers where the org has at least one player registered
            res = cur.execute("SELECT COUNT (DISTINCT tier) FROM players WHERE org = ?", (org,))
            num_teams = res.fetchone()[0]
            data[org]["points"] = round(data[org]["points"] / num_teams, 2)
        else:
            data[org]["points"] = round(data[org]["points"], 1)

        # If a value is a float that is representing an integer (e.g 7.0), make it an integer
        # such that it displays as 7
        if isinstance(data[org]["points"], float) and data[org]["points"].is_integer():
            data[org]["points"] = int(data[org]["points"])

    logger.info("Finished querying database for org data")

    return data


def update(tiers):
    # For each tier that needs a graphic generating, get the data, then edit the graphic
    for tier in tiers:
        logger.info(f"Generating standings graphic for {tier}")
        data = get_data(tier)
        edit_graphic(tier, data)


update(["Overall"])
