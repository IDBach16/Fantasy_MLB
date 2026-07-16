"""
Ottoneu keeper/salary value layer (league 907, Old School 5x5).

Surplus value = Ottoneu AVERAGE salary (market price for this game type) - YOUR salary.
Positive surplus = bargain keep; negative = overpaid (cut/trade). Layered with 2026
Savant (xwOBA over/under) to catch players whose market price is about to move.
"""
import io
import os
import pandas as pd

from . import players as PL
from . import savant as SV
from . import prospects as PR

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
MY_TEAM = "6418"


def _strip_team(name):
    toks = str(name).split()
    if toks and toks[-1].isupper() and 2 <= len(toks[-1]) <= 4:
        toks = toks[:-1]
    return PL._norm(" ".join(toks))


def _money(s):
    return pd.to_numeric(str(s).replace("$", "").replace(",", ""), errors="coerce")


def load_avg_values(refresh=False) -> pd.DataFrame:
    cache_file = os.path.join(CACHE, "ottoneu_avg_values_907.csv")
    if not refresh and os.path.exists(cache_file):
        return pd.read_csv(cache_file)
    from connectors.ottoneu import OttoneuConnector
    with OttoneuConnector(headless=False) as c:
        html = c.fetch_checked("/907/averageValues", expect="Name")
    t = pd.read_html(io.StringIO(html))[0]
    for col in ["Average", "Median", "Minimum", "Maximum", "Last 10"]:
        if col in t.columns:
            t[col] = t[col].map(_money)
    t["norm"] = t["Name"].map(_strip_team)
    t.to_csv(cache_file, index=False)
    return t


def my_roster_value(refresh=False) -> pd.DataFrame:
    roster = PR.ottoneu_full_roster(refresh=refresh)
    mine = roster[roster["TeamID"].astype(str) == MY_TEAM].copy()
    mine["salary"] = mine["Salary"].map(_money)
    mine["norm"] = mine["Name"].map(PL._norm)
    mine["mlbam"] = mine["FG MajorLeagueID"].map(PL.fg_to_mlbam)

    avg = load_avg_values(refresh=refresh)[["norm", "Average", "Median", "Roster%"]]
    df = mine.merge(avg, on="norm", how="left")
    df["surplus"] = (df["Average"] - df["salary"]).round(1)

    # 2026 production signal (xwOBA over/under)
    bat = SV.batting_expected(2026)[["player_id", "pa", "woba", "est_woba"]].copy()
    bat["player_id"] = pd.to_numeric(bat["player_id"], errors="coerce")
    pit = SV.pitching_expected(2026)[["player_id", "pa", "woba", "est_woba"]].copy()
    pit.columns = ["player_id", "p_pa", "p_woba", "p_est_woba"]
    pit["player_id"] = pd.to_numeric(pit["player_id"], errors="coerce")
    df["mlbam"] = pd.to_numeric(df["mlbam"], errors="coerce")
    df = df.merge(bat, left_on="mlbam", right_on="player_id", how="left").drop(columns=["player_id"])
    df = df.merge(pit, left_on="mlbam", right_on="player_id", how="left").drop(columns=["player_id"])

    out = df[["Name", "Position(s)", "salary", "Average", "surplus", "Roster%",
              "pa", "woba", "est_woba", "p_pa", "p_woba", "p_est_woba"]]
    out = out.rename(columns={"Name": "player", "Position(s)": "pos", "Average": "avg_salary"})
    return out.sort_values("surplus", ascending=False)
