def extract_game_state(game_doc):
    return {
        "inning": game_doc.get("current_inning"),
        "outs": game_doc.get("outs"),
        "score_diff": abs(game_doc.get("home_score", 0) - game_doc.get("away_score", 0)),
        "is_tied": game_doc.get("home_score") == game_doc.get("away_score"),
        "half": game_doc.get("inning_half"),  # "Top" or "Bottom"
        "runners_on": game_doc.get("runners_on_base", [])  # list of bases: ["1B", "2B"]
    }

def is_high_leverage(game_state):
    return (
        game_state.get("inning") == 9 and
        game_state.get("outs") == 2 and
        game_state.get("score_diff") == 0
    )
