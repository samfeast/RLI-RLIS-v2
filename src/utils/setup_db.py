import os
import sqlite3


def main():
    def create_blank_db():
        con = sqlite3.connect("../../data/rlis_data.db")
        cur = con.cursor()
        cur.execute(
            """CREATE TABLE players(
            id INTEGER, 
            status TEXT, 
            name TEXT NOT NULL, 
            platform TEXT NOT NULL, 
            platform_id TEXT NOT NULL, 
            tier TEXT, 
            org TEXT,
            PRIMARY KEY(id, status)
            ) STRICT"""
        )
        cur.execute(
            """CREATE TABLE fixtures(
            week INTEGER, 
            tier TEXT, 
            org_1 INTEGER, 
            org_2 INTEGER, 
            PRIMARY KEY(week, tier, org_1, org_2)
            ) STRICT"""
        )
        cur.execute(
            """CREATE TABLE series_log(
            timestamp INTEGER NOT NULL, 
            game_id INTEGER PRIMARY KEY, 
            tier TEXT NOT NULL, 
            mode INTEGER NOT NULL, 
            winning_org TEXT NOT NULL, 
            losing_org TEXT NOT NULL, 
            games_won_by_loser INTEGER NOT NULL, 
            played_previously INTEGER NOT NULL,
            replays_stored INTEGER,
            published INTEGER NOT NULL
            ) STRICT"""
        )

        cur.execute(
            """CREATE TABLE series_players(
            game_id INTEGER PRIMARY KEY, 
            wp1 TEXT, 
            wp2 TEXT, 
            wp3 TEXT, 
            lp1 TEXT, 
            lp2 TEXT, 
            lp3 TEXT,
            FOREIGN KEY(game_id) REFERENCES series_log(game_id) ON DELETE CASCADE
            ) STRICT"""
        )

        cur.execute(
            """CREATE TABLE game_stats(
            guid TEXT PRIMARY KEY, 
            url TEXT NOT NULL, 
            timestamp INTEGER NOT NULL, 
            game_id INTEGER NOT NULL,
            winning_org TEXT NOT NULL,
            losing_org TEXT NOT NULL,
            duration REAL, 
            overtime_duration REAL, 
            winner_goals INTEGER, 
            loser_goals INTEGER, 
            time_in_side_winner REAL, 
            time_in_side_loser REAL, 
            FOREIGN KEY(game_id) REFERENCES series_log(game_id) ON DELETE CASCADE
            ) STRICT"""
        )
        cur.execute(
            """CREATE TABLE player_stats(
           guid TEXT NOT NULL, 
           name TEXT NOT NULL, 
           game_id INTEGER NOT NULL,
           duration REAL,
           goals INTEGER, 
           assists INTEGER, 
           saves INTEGER, 
           shots INTEGER, 
           score INTEGER, 
           demos_inflicted INTEGER, 
           demos_taken INTEGER,
           car TEXT, 
           boost_while_ss INTEGER, 
           time_0_boost REAL, 
           avg_speed REAL, 
           dist_travelled INTEGER,
           PRIMARY KEY(guid, name),
           FOREIGN KEY(guid) REFERENCES game_stats(guid) ON DELETE CASCADE
           ) STRICT"""
        )

        cur.execute(
            """CREATE TABLE stats_stack(
            priority INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL,
            replay_id TEXT,
            start_timestamp INTEGER,
            end_timestamp INTEGER,
            winning_org TEXT,
            losing_org TEXT,
            p_out TEXT,
            alt_platform TEXT,
            alt_platform_id TEXT,
            FOREIGN KEY(game_id) REFERENCES series_log(game_id) ON DELETE CASCADE
            ) STRICT"""
        )
        con.commit()

        print("Database created")

    if os.path.exists("../../data/rlis_data.db"):
        confirmation = input(
            "rlis_data.db already exists. Type 'Y' to delete it and create a new, blank database: "
        )
        if confirmation.lower() == "y":
            os.remove("../../data/rlis_data.db")
            if os.path.exists("../../data/rlis_data.db-shm"):
                os.remove("../../data/rlis_data.db-shm")
            if os.path.exists("../../data/rlis_data.db-wal"):
                os.remove("../../data/rlis_data.db-wal")
            create_blank_db()
    else:
        create_blank_db()


if __name__ == "__main__":
    main()
