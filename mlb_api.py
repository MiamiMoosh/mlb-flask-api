import requests

def get_live_game_state(game_pk):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    res = requests.get(url)
    if res.status_code != 200:
        return None

    data = res.json()
    live = data.get("liveData", {}).get("plays", {}).get("currentPlay", {})
    box = data.get("liveData", {}).get("boxscore", {})
    linescore = data.get("liveData", {}).get("linescore", {})
    status = data.get("gameData", {}).get("status", {})

    return {
        "inning": linescore.get("currentInning"),
        "inning_half": linescore.get("inningHalf"),
        "outs": live.get("count", {}).get("outs", 0),
        "home_score": linescore.get("teams", {}).get("home", {}).get("runs"),
        "away_score": linescore.get("teams", {}).get("away", {}).get("runs"),
        "runners": [r.get("base") for r in live.get("runners", [])],
        "game_status": status.get("detailedState", "Scheduled")
    }
