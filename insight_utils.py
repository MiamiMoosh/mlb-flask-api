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