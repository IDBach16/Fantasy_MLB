"""
Risk signals per rostered player:
  - luck / regression: season wOBA vs xwOBA gap (+ = overperforming, will fall)
  - recent trend: 3/7/30-day (hitters) or 3/6/9-outing (pitchers) vs season
  - playing-time / injury proxy: games in the last 7 days (hitter); recent outings (pitcher)
  - explicit injury status: ESPN only (espn-api injuryStatus)
"""
import pandas as pd

from . import analyze as A
from . import rosters as R
from . import mlb_live as ML


def _espn_injuries():
    try:
        from analysis.lineups import espn_lineup
        df = espn_lineup()
        return {str(r["player"]): r.get("injury") for _, r in df.iterrows()}
    except Exception:
        return {}


def league_risk(platform):
    df = A.merge_savant(R.load_all(refresh=False))
    d = df[df["platform"] == platform].copy()
    d["xwoba"] = d["est_woba"].fillna(d["p_est_woba"])
    d["woba_a"] = d["woba"].fillna(d["p_woba"])
    d["gap"] = (d["woba_a"] - d["xwoba"]).round(3)
    d["samp"] = d["pa"].fillna(d["p_pa"])

    tw = {t["player"]: t for t in ML.recent_windows(d)}
    inj = _espn_injuries() if platform == "espn" else {}

    rows = []
    for _, r in d.iterrows():
        t = tw.get(r["player"], {})
        rec = {"player": r["player"], "positions": r.get("positions"),
               "is_pitcher": bool(r["is_pitcher"]),
               "xwoba": None if pd.isna(r["xwoba"]) else round(float(r["xwoba"]), 3),
               "woba": None if pd.isna(r["woba_a"]) else round(float(r["woba_a"]), 3),
               "gap": None if pd.isna(r["gap"]) else r["gap"],
               "samp": None if pd.isna(r["samp"]) else int(r["samp"]),
               "injury": inj.get(str(r["player"]))}
        if r["is_pitcher"]:
            rec["recent_outings_3"] = t.get("o3")
            rec["recent_outings_9"] = t.get("o9")
        else:
            d7 = t.get("d7") or {}
            rec["games_last_7d"] = d7.get("games")
            rec["last_3d"] = t.get("d3")
            rec["last_30d"] = t.get("d30")
        rows.append(rec)
    return rows
