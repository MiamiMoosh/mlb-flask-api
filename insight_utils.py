from pybaseball import statcast_batter, statcast_pitcher
import statsapi
import datetime

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