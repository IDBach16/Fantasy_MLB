"""
League-wide keeper-context for realistic trades: every team's CAP situation
(used / space / open spots) and condensed roster (players + salary + xwOBA + luck gap).
Lets the trade agent reason about who can absorb salary, who's a likely seller, and
which teams' needs match my surplus.
"""
import pandas as pd

from . import trade_targets as TT

CAP = 400
ROSTER_MAX = 40


def team_caps(lv=None) -> pd.DataFrame:
    lv = lv if lv is not None else TT.league_value()
    g = (lv.groupby(["team", "team_id"], dropna=False)
         .agg(cap_used=("salary", "sum"), players=("player", "count")).reset_index())
    g["cap_used"] = g["cap_used"].round(0)
    g["cap_space"] = (CAP - g["cap_used"]).round(0)
    g["spots_open"] = ROSTER_MAX - g["players"]
    return g.sort_values("cap_space", ascending=False)


def condensed_rosters(lv=None, per_team=12):
    """Each team's core (top players by salary) with value — bounded for payload size."""
    lv = lv if lv is not None else TT.league_value()
    out = {}
    for team, grp in lv.groupby("team"):
        g = grp.sort_values("salary", ascending=False).head(per_team)
        recs = g[["player", "pos", "salary", "xwoba", "gap"]].round(3)
        recs = recs.astype(object).where(pd.notnull(recs), None)
        out[str(team)] = recs.to_dict("records")
    return out
