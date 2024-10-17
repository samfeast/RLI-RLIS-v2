import os
import csv
import sqlite3


def main():
    def load_players():
        con = sqlite3.connect("../../data/rlis_data.db")
        cur = con.cursor()

        num_players = 0
        with open("../../data/player_info.csv", "r") as csv_file:
            reader = csv.reader(csv_file, delimiter=",")

            for row in reader:
                # First value in each row is discord ID which should be an integer,
                # if it is not then it must be the header row, so ignore it
                if row[0].isdigit():
                    num_players += 1
                    cur.execute(
                        "INSERT INTO players VALUES(?, ?, ?, ?, ?, ?)",
                        (int(row[0]), row[1], row[2], row[3], row[4], row[5]),
                    )

        con.commit()

        print(f"{num_players} players loaded")

    if os.path.exists("../../data/rlis_data.db"):
        load_players()
    else:
        print("Database does not exist")


if __name__ == "__main__":
    main()
