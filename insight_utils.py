from pybaseball import statcast_batter, statcast_pitcher
import statsapi
import datetime

def generate_matchup_insight(batter_name, pitcher_name, days_back=14):
    try:
        # Look up MLBAM IDs
        batter_id = statsapi.lookup_player(batter_name)[0]["id"]
        pitcher_id = statsapi.lookup_player(pitcher_name)[0]["id"]
    except (IndexError, KeyError):
        return {"error": f"Could not find player ID for {batter_name} or {pitcher_name}."}

    today = datetime.date.today()
    start = today - datetime.timedelta(days=days_back)
    start_str = start.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    # Fetch Statcast data
    batter_df = statcast_batter(start_str, end_str, batter_id)
    pitcher_df = statcast_pitcher(start_str, end_str, pitcher_id)

    # Analyze pitcher pitch mix
    pitch_mix = pitcher_df["pitch_type"].value_counts(normalize=True).head(3)

    insights = []
    for pitch in pitch_mix.index:
        batter_vs_pitch = batter_df[batter_df["pitch_type"] == pitch]
        if batter_vs_pitch.empty:
            continue

        avg_ev = round(batter_vs_pitch["launch_speed"].mean(), 1)
        whiffs = batter_vs_pitch["description"].fillna("").str.contains("swinging_strike").sum()
        total = len(batter_vs_pitch)
        whiff_rate = f"{round((whiffs / total) * 100)}%" if total else "N/A"

        insights.append(f"{batter_name} avg EV vs {pitch}: {avg_ev} mph, whiff rate: {whiff_rate}")

    return {
        "pitcher_pitch_mix": pitch_mix.to_dict(),
        "batter_vs_pitch_types": insights
    }

def get_player_id(name):
    try:
        return statsapi.lookup_player(name)[0]["id"]
    except:
        return None

def get_recent_batter_insight(name):
    pid = get_player_id(name)
    if not pid:
        return f"No player found for {name}."

    today = datetime.date.today()
    start = today - datetime.timedelta(days=14)
    data = statcast_batter(start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), pid)

    if data.empty:
        return f"{name} has no Statcast data in the last 2 weeks."

    hr = data["events"].fillna("").str.contains("home_run").sum()
    avg_ev = round(data["launch_speed"].mean(), 1)
    return f"{name} has hit {hr} HR with an average exit velo of {avg_ev} mph in the last 2 weeks."

def get_pitcher_mix(name):
    pid = get_player_id(name)
    if not pid:
        return f"No player found for {name}."

    today = datetime.date.today()
    start = today - datetime.timedelta(days=30)
    data = statcast_pitcher(start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), pid)

    if data.empty:
        return f"{name} has no Statcast pitching data in the last 30 days."

    mix = data["pitch_type"].value_counts(normalize=True).head(3)
    return f"{name}'s pitch mix: " + ", ".join([f"{k} ({round(v*100)}%)" for k, v in mix.items()])

def extract_matchup_pair(game_id, game_doc):
    """Returns (batter, pitcher) tuple using best available info, or (None, None)."""
    if not game_doc:
        return None, None

    home = game_doc.get("home_team")
    away = game_doc.get("away_team")
    probable = game_doc.get("probable_pitchers", {})
    lineups = game_doc.get("batting_orders", {})

    teams = game_id.split("-")[-2:]
    home_abbr = home if home in teams else None
    away_abbr = away if away in teams else None

    if not home_abbr or not away_abbr:
        return None, None

    pitcher = probable.get("away")
    batter_list = lineups.get("home")

    if pitcher and batter_list and len(batter_list) > 0:
        return batter_list[0], pitcher

    pitcher_alt = probable.get("home")
    batter_list_alt = lineups.get("away")
    if pitcher_alt and batter_list_alt and len(batter_list_alt) > 0:
        return batter_list_alt[0], pitcher_alt

    any_pitcher = (probable.get("home") or probable.get("away"))
    any_batter = (lineups.get("home") or lineups.get("away") or [])
    if any_pitcher and any_batter:
        return any_batter[0], any_pitcher

    return None, None