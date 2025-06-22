import requests
import datetime, UTC
import logging

API_KEY = "1"  # Free tier key for TheSportsDB
BASE = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"

# === Config Flags ===
ENABLE_PLAYER_DETAILS = True
ENABLE_LIVE_STATUS_INFERENCE = True
ENABLE_LOGO_AND_STADIUM = True
ENABLE_CACHE = True

# === In-memory cache ===
_cache = {}

def fetch_json(endpoint, params=None, ttl=30):
    """Handles GET requests with optional memory cache."""
    url = f"{BASE}/{endpoint}"
    cache_key = f"{endpoint}:{str(params)}"

    if ENABLE_CACHE and cache_key in _cache:
        cached = _cache[cache_key]
        if (datetime.now(UTC) - cached["ts"]).total_seconds() < ttl:
            return cached["data"]

    try:
        res = requests.get(url, params=params, timeout=6)
        res.raise_for_status()
        data = res.json()
        if ENABLE_CACHE:
            _cache[cache_key] = {"data": data, "ts": datetime.now(UTC)}
        return data
    except Exception as e:
        logging.warning(f"❌ Fetch error: {url} • {e}")
        return {}

# === Data Normalization ===
def normalize_event(e):
    start_time = f"{e['dateEvent']}T{e.get('strTime') or '00:00:00'}"
    status = infer_status(e)

    return {
        "game_id": e.get("idEvent"),
        "event_name": e.get("strEvent"),
        "home_team": e.get("strHomeTeam"),
        "away_team": e.get("strAwayTeam"),
        "home_score": safe_int(e.get("intHomeScore")),
        "away_score": safe_int(e.get("intAwayScore")),
        "status": status,
        "start_time": start_time,
        "league": e.get("strLeague"),
        "season": e.get("strSeason"),
        "venue": e.get("strVenue"),
        "sport": e.get("strSport"),
        "badge_urls": get_team_logos(e) if ENABLE_LOGO_AND_STADIUM else {},
        "stadium_thumb": get_stadium_thumb(e.get("strVenue")) if ENABLE_LOGO_AND_STADIUM else None,
        "players": get_players_for_event(e["idEvent"]) if ENABLE_PLAYER_DETAILS else [],
    }

def infer_status(e):
    if not ENABLE_LIVE_STATUS_INFERENCE:
        return e.get("strStatus") or "Unknown"

    try:
        now = datetime.now(UTC).date()
        event_date = datetime.datetime.strptime(e["dateEvent"], "%Y-%m-%d").date()
        if e.get("intHomeScore") is not None:
            return "Final"
        elif event_date == now:
            return "In Progress"
        else:
            return "Scheduled"
    except:
        return e.get("strStatus") or "Unknown"

# === Player Details ===
def get_players_for_event(event_id):
    data = fetch_json("lookupeventplayers.php", {"id": event_id})
    return [{
        "id": p.get("idPlayer"),
        "name": p.get("strPlayer"),
        "team": p.get("strTeam"),
        "number": p.get("strNumber"),
        "position": p.get("strPosition"),
        "thumb": p.get("strThumb"),
    } for p in data.get("player", [])]

# === Logo and Stadium Helpers ===
def get_team_logos(e):
    logos = {}
    league = e.get("strLeague")
    if not league:
        return logos

    data = fetch_json("search_all_teams.php", {"l": league})
    for t in data.get("teams", []):
        logos[t.get("strTeam")] = t.get("strTeamBadge")
    return {
        "home_logo": logos.get(e.get("strHomeTeam")),
        "away_logo": logos.get(e.get("strAwayTeam")),
    }

def get_stadium_thumb(venue_name):
    if not venue_name:
        return None
    data = fetch_json("searchvenues.php", {"v": venue_name})
    venues = data.get("venues")
    return venues[0].get("strThumb") if venues else None

# === Public API ===
def get_games_for_league(league_id, mode="next"):
    endpoint = "eventsnextleague.php" if mode == "next" else "eventspastleague.php"
    raw = fetch_json(endpoint, {"id": league_id})
    return [normalize_event(e) for e in raw.get("events", []) if e]

def get_leagues():
    data = fetch_json("all_leagues.php")
    return [{
        "id": l["idLeague"],
        "name": l["strLeague"],
        "sport": l["strSport"]
    } for l in data.get("leagues", []) if l]