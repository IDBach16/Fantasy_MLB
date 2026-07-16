"""
Bauers Fight Club team snapshot from Ottoneu: standings (rank/category points),
1/7/30-day point change (momentum), games-played by position (pace), and the team
page hitter/pitcher tables (G / PA / IP for pace + production).
"""
import io
import pandas as pd

LID, TID, TEAM = "907", "6418", "Bauers Fight Club"


def _records(df):
    return df.fillna("").astype(object).to_dict("records")


def snapshot():
    from connectors.ottoneu import OttoneuConnector
    with OttoneuConnector(headless=False) as c:
        sthtml = c.fetch_checked(f"/{LID}/standings")
        thtml = c.fetch_checked(f"/{LID}/team/{TID}")
    st = pd.read_html(io.StringIO(sthtml))
    tt = pd.read_html(io.StringIO(thtml))
    return {
        "standings_categories": _records(st[0]) if len(st) > 0 else [],
        "standings_totals": _records(st[1]) if len(st) > 1 else [],
        "points_change_1_7_30_day": _records(st[2]) if len(st) > 2 else [],
        "games_played_by_position": _records(st[3]) if len(st) > 3 else [],
        "my_hitters": _records(tt[0]) if len(tt) > 0 else [],
        "my_pitchers": _records(tt[1]) if len(tt) > 1 else [],
    }
