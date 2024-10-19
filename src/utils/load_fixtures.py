import os
import csv
import sqlite3
import json

with open("../../config.json", "r") as read_file:
    config = json.load(read_file)

ORGS = config["ORGS"]


def main():
    def load_fixtures():
        con = sqlite3.connect("../../data/rlis_data.db")
        cur = con.cursor()

        num_fixtures = 0
        with open("../../data/fixtures.csv", "r") as csv_file:
            reader = csv.reader(csv_file, delimiter=",")

            for row in reader:
                # First value in each row is discord ID which should be an integer,
                # if it is not then it must be the header row, so ignore it
                if row[0].isdigit():
                    num_fixtures += 1
                    org_1_id = ORGS[row[2]]["id"]
                    org_2_id = ORGS[row[3]]["id"]
                    cur.execute(
                        "INSERT INTO fixtures VALUES(?, ?, ?, ?)",
                        (int(row[0]), row[1], org_1_id, org_2_id),
                    )

        con.commit()

        print(f"{num_fixtures} players loaded")

    if os.path.exists("../../data/rlis_data.db"):
        load_fixtures()
    else:
        print("Database does not exist")


if __name__ == "__main__":
    main()
