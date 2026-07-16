"""
Cross-reference Prospect Savant with Ottoneu rosters to rank AVAILABLE prospects
to target. Join is by MinorMasterId == Ottoneu 'FG MinorLeagueID' (exact id, no
fuzzy matching). Available = in Prospect Savant but NOT on any Ottoneu roster.
"""
import io
import os
import pandas as pd

from connectors import prospect_savant as PS

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
OTTO_LEAGUE = "907"


def ps_universe(refresh=False) -> pd.DataFrame:
    h = PS.pull_all("hitters", 2026, refresh=refresh)
    p = PS.pull_all("pitchers", 2026, refresh=refresh)
    h = h.assign(ptype="H")
    p = p.assign(ptype="P")
    df = pd.concat([h, p], ignore_index=True)
    df["pscore"] = pd.to_numeric(df["pscore"], errors="coerce")
    # promoted players appear at multiple levels -> keep their best PS Score row
    df = df.sort_values("pscore", ascending=False).drop_duplicates("MinorMasterId", keep="first")
    return df


def ottoneu_full_roster(refresh=False) -> pd.DataFrame:
    cache_file = os.path.join(CACHE, "ottoneu_full_roster_907.csv")
    if not refresh and os.path.exists(cache_file):
        return pd.read_csv(cache_file)
    from connectors.ottoneu import OttoneuConnector
    with OttoneuConnector(headless=False) as c:
        text = c.roster_export(OTTO_LEAGUE)
    r = pd.read_csv(io.StringIO(text))
    r.to_csv(cache_file, index=False)
    return r


def available_prospects(refresh=False) -> pd.DataFrame:
    uni = ps_universe(refresh=refresh)
    roster = ottoneu_full_roster(refresh=refresh)
    rostered_ids = set(roster["FG MinorLeagueID"].dropna().astype(str))
    uni["rostered_in_ottoneu"] = uni["MinorMasterId"].astype(str).isin(rostered_ids)
    avail = uni[~uni["rostered_in_ottoneu"]].sort_values("pscore", ascending=False)
    return avail


def my_prospects(refresh=False) -> pd.DataFrame:
    """PS Scores for prospects on the user's Ottoneu team (6418)."""
    uni = ps_universe(refresh=refresh)
    roster = ottoneu_full_roster(refresh=refresh)
    mine = roster[roster["TeamID"].astype(str) == "6418"]
    ids = set(mine["FG MinorLeagueID"].dropna().astype(str))
    return uni[uni["MinorMasterId"].astype(str).isin(ids)].sort_values("pscore", ascending=False)
