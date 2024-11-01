import os
import csv
import sqlite3
import json

with open("../../config.json", "r") as read_file:
    config = json.load(read_file)

ORGS = config["ORGS"]


def main():
    def load_results():
        con = sqlite3.connect("../../data/rlis_data.db")
        cur = con.cursor()

        # Referential integrity constraints are not enforced as this is considered a setup operation

        cur.execute("DELETE FROM series_log")
        cur.execute("DELETE FROM series_players")

        num_series = 0
        with open("../../data/series_log.csv", "r") as csv_file:
            reader = csv.reader(csv_file, delimiter=",")

            for row in reader:
                # First value in each row is timestamp which should be an integer,
                # if it is not then it must be the header row, so ignore it
                if row[0].isdigit():
                    num_series += 1
                    cur.execute(
                        "INSERT INTO series_log VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            int(row[0]),
                            row[1],
                            row[2],
                            row[3],
                            row[4],
                            row[5],
                            row[6],
                            row[7],
                            None,
                            0,
                        ),
                    )

        num_series_players = 0
        with open("../../data/series_players.csv", "r") as csv_file:
            reader = csv.reader(csv_file, delimiter=",")

            for row in reader:
                row = [None if r == "" else r for r in row]
                print(row)
                # First value in each row is game_id which should be an integer,
                # if it is not then it must be the header row, so ignore it
                if row[0].isdigit():
                    num_series_players += 1
                    cur.execute(
                        "INSERT INTO series_players VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (row[0], row[1], row[2], row[3], row[4], row[5], row[6]),
                    )

        con.commit()

        print(f"{num_series} series and {num_series_players} series players loaded")

    if os.path.exists("../../data/rlis_data.db"):
        load_results()
    else:
        print("Database does not exist")


if __name__ == "__main__":
    main()
