from sportsdb_api import get_games_for_league
from pymongo import MongoClient
from datetime import datetime

LEAGUE_IDS = ["4387", "4391", "4394", "4424", "4457"]  # NBA, NFL, etc.
client = MongoClient()
db = client["your-db"]
threadline_games = db.threadline_games


def seed_games():
    today = datetime.now(UTC).date().isoformat()
    threadline_games.delete_many({"date": today})

    for lid in LEAGUE_IDS:
        games = get_games_for_league(lid, mode="next")
        for g in games:
            if g["start_time"].startswith(today):
                threadline_games.insert_one({
                    "game_id": g["game_id"],
                    "date": today,
                    "scheduled_time": g["start_time"][11:16],
                    "home_team": g["home_team"],
                    "away_team": g["away_team"],
                    "league": g["league"],
                    "sport": g["sport"]
                })


if __name__ == "__main__":
    seed_games()
