import os
import sqlite3


def main():
    def create_blank_db():
        con = sqlite3.connect("../../data/rlis_data.db")
        cur = con.cursor()
        cur.execute("CREATE TABLE players(id, name, platform, platform_id, tier, org)")
        cur.execute("CREATE TABLE subs(id, name, platform, platform_id)")
        cur.execute("CREATE TABLE fixtures(week, tier, org_1, org_2)")
        cur.execute(
            """CREATE TABLE series_log_1v1(
            timestamp, game_id, tier, winning_org, losing_org, 
            games_won_by_loser, played_previously,
            wp1, lp1, 
            guid_1, guid_2, guid_3)"""
        )
        cur.execute(
            """CREATE TABLE series_log_2v2(
            timestamp, game_id, tier, winning_org, losing_org, 
            games_won_by_loser, played_previously,
            wp1, wp2, lp1, lp2,
            guid_1, guid_2, guid_3)"""
        )
        cur.execute(
            """CREATE TABLE series_log_3v3(
            timestamp, game_id, tier, winning_org, losing_org, 
            games_won_by_loser, played_previously,
            wp1, wp2, wp3, lp1, lp2, lp3, 
            guid_1, guid_2, guid_3, guid_4, guid_5)"""
        )
        cur.execute(
            """CREATE TABLE game_stats(
            guid, url, timestamp, game_id, 
            overtime_duration, winner_goals, losing_goals)"""
        )
        cur.execute(
            """CREATE TABLE player_stats(
            guid, id, game_id, 
            score, goals, assists, saves, shots)"""
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
