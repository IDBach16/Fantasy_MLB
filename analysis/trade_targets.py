"""
League-wide trade value for Ottoneu 907. Every rostered player (all 12 teams) with
salary, Ottoneu market (avg) salary, surplus, and 2026 xwOBA over/under-performance.
Powers the trade agent: buy-low targets on other teams + your sell-high chips.
"""
import pandas as pd

from . import players as PL
from . import savant as SV
from . import ottoneu_salary as OS
from . import prospects as PR

MY_TEAM = "6418"


def league_value() -> pd.DataFrame:
    roster = PR.ottoneu_full_roster().copy()
    roster["salary"] = roster["Salary"].map(OS._money)
    roster["mlbam"] = pd.to_numeric(roster["FG MajorLeagueID"].map(PL.fg_to_mlbam), errors="coerce")
    roster["norm"] = roster["Name"].map(PL._norm)

    avg = OS.load_avg_values()[["norm", "Average"]]
    df = roster.merge(avg, on="norm", how="left")
    df["surplus"] = (df["Average"] - df["salary"]).round(1)

    bat = SV.batting_expected(2026)[["player_id", "pa", "woba", "est_woba"]].copy()
    bat["player_id"] = pd.to_numeric(bat["player_id"], errors="coerce")
    pit = SV.pitching_expected(2026)[["player_id", "pa", "woba", "est_woba"]].copy()
    pit.columns = ["player_id", "p_pa", "p_woba", "p_est_woba"]
    pit["player_id"] = pd.to_numeric(pit["player_id"], errors="coerce")

    df = df.merge(bat, left_on="mlbam", right_on="player_id", how="left").drop(columns=["player_id"])
    df = df.merge(pit, left_on="mlbam", right_on="player_id", how="left").drop(columns=["player_id"])
    df["xwoba"] = df["est_woba"].fillna(df["p_est_woba"])
    df["woba_actual"] = df["woba"].fillna(df["p_woba"])
    df["gap"] = (df["woba_actual"] - df["xwoba"]).round(3)   # + overperform(sell), - underperform(buy)
    df["samp"] = df["pa"].fillna(df["p_pa"])

    out = df[["Name", "Team Name", "TeamID", "Position(s)", "salary", "Average", "surplus",
              "xwoba", "woba_actual", "gap", "samp"]]
    return out.rename(columns={"Name": "player", "Team Name": "team", "TeamID": "team_id",
                               "Position(s)": "pos", "Average": "avg_salary"})


def buy_low_targets(df=None, n=25, min_pa=80):
    """Other-team players UNDER-performing their xwOBA (woba << xwoba) = buy-low."""
    df = df if df is not None else league_value()
    other = df[(df["team_id"].astype(str) != MY_TEAM) & (df["samp"] >= min_pa) & df["xwoba"].notna()]
    return other.sort_values("gap").head(n)   # most negative gap = most unlucky


def my_sell_high(df=None, min_pa=60):
    """My players OVER-performing their xwOBA (woba >> xwoba) = sell-high chips."""
    df = df if df is not None else league_value()
    mine = df[(df["team_id"].astype(str) == MY_TEAM) & (df["samp"] >= min_pa) & df["xwoba"].notna()]
    return mine.sort_values("gap", ascending=False)
